"""ADK agent tools for managing the current workflow session's WorkflowTasks.

These callables are attached to the skill-driven workflow agent (see
:func:`infrastructure.agent.create_agent`) so it can register a plan as a
WorkflowTask DAG and then iterate the tasks, updating their status as it works.

Two facts shape the implementation:

* The tools run *during* the AG-UI SSE stream, outside FastAPI's per-request
  dependency-injection scope, so each call opens its own ``AsyncSession`` on the
  module-level engine rather than receiving an injected session.
* A single ``ADKAgent`` is cached per skill and serves every session that uses
  that skill, so the tools cannot capture a specific ``workflow_session_id`` at
  agent-creation time. Instead they resolve it at call time by mapping the ADK
  session id (the AG-UI thread id, stored on ``WorkflowSession.session_id``)
  back to the WorkflowSession primary key via
  :meth:`WorkflowSessionRepository.get_by_session_id`.

Every tool returns plain JSON-serializable values (``dict``/``list``) so the LLM
can consume them, mapping repository errors to an ``{"error": ...}`` payload the
agent can react to instead of raising.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from models.notification import NotificationCreate, NotificationType
from models.workflow_task import (
    ToolBinding,
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskStatus,
    WorkflowTaskUpdate,
)
from repositories import (
    NotificationRepository,
    SqlMCPServerRepository,
    SqlNotificationRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

_NO_SESSION = "no workflow session is bound to the current run; cannot manage tasks"


@asynccontextmanager
async def _repos() -> AsyncIterator[
    tuple[WorkflowSessionRepository, WorkflowTaskRepository, NotificationRepository]
]:
    """Open a database session and yield the session, task, and notification repos.

    Opens a fresh ``AsyncSession`` on the module-level engine (the tools run
    outside FastAPI's request scope) and wires a WorkflowSession repository, a
    WorkflowTask repository, and a Notification repository to it. The engine is
    referenced through the ``database`` module so tests can monkeypatch
    ``database.engine``.

    Yields:
        A ``(workflow_session_repository, workflow_task_repository,
        notification_repository)`` tuple bound to the same session.
    """
    async with AsyncSession(database.engine) as db:
        ws_repo = SqlWorkflowSessionRepository(db)
        yield (
            ws_repo,
            SqlWorkflowTaskRepository(db, ws_repo, SqlMCPServerRepository(db)),
            SqlNotificationRepository(db),
        )


async def _resolve_ws_id(
    tool_context: ToolContext, ws_repo: WorkflowSessionRepository
) -> str | None:
    """Resolve the current run's WorkflowSession primary key, or ``None``.

    Reads the ADK session id from ``tool_context.session.id`` and maps it to the
    owning WorkflowSession's primary key, which is the foreign key target for
    WorkflowTask records.

    Args:
        tool_context: The ADK tool context for the current invocation.
        ws_repo: Repository used to look the session up by its ADK session id.

    Returns:
        The WorkflowSession primary key, or ``None`` if the session id is missing
        or no WorkflowSession matches it.
    """
    session = getattr(tool_context, "session", None)
    session_id = getattr(session, "id", None)
    if not session_id:
        return None
    ws = await ws_repo.get_by_session_id(session_id)
    return ws.id if ws is not None else None


def _user_id(tool_context: ToolContext) -> str:
    """Return the caller's user id for audit fields, defaulting to ``"user"``."""
    return getattr(tool_context, "user_id", None) or "user"


#: WorkflowTask statuses that count as "done" for session-completion detection.
_TERMINAL_STATUSES = frozenset(
    {
        WorkflowTaskStatus.completed,
        WorkflowTaskStatus.failed,
        WorkflowTaskStatus.skipped,
    }
)


async def _notify(
    ws_repo: WorkflowSessionRepository,
    notif_repo: NotificationRepository,
    ws_id: str,
    notification_type: NotificationType,
    title: str,
    body: str | None = None,
    recipient: str | None = None,
) -> None:
    """Create a notification addressed to ``recipient`` (default: the session owner).

    When ``recipient`` is omitted the notification is addressed to the session's
    ``created_by`` (the real user who started the session); pass ``recipient`` to
    target a different user, such as an approval request's designated approver.
    The audit user is always the session's ``created_by``, which keeps the
    ``created_by`` foreign key valid even though the tool's own ``tool_context``
    user id may be a placeholder. Notification creation is best-effort: any failure
    is logged and swallowed so a notification problem never breaks the task
    operation that triggered it.

    Args:
        ws_repo: Repository used to resolve the session and its owner.
        notif_repo: Repository used to persist the notification.
        ws_id: Primary key of the workflow session the notification concerns.
        notification_type: The kind of event being announced.
        title: Short headline shown in the notification panel.
        body: Optional longer description.
        recipient: User id to address the notification to; defaults to the
            session owner when ``None``.
    """
    try:
        ws = await ws_repo.get(ws_id)
        if ws is None:
            return
        data = NotificationCreate(
            user_id=recipient or ws.created_by,
            type=notification_type,
            title=title,
            body=body,
            workflow_session_id=ws_id,
        )
        await notif_repo.create(data, user_id=ws.created_by)
    except Exception:
        logger.exception(
            "failed to create %s notification for workflow session %s",
            notification_type,
            ws_id,
        )


async def _maybe_notify_session_completed(
    ws_repo: WorkflowSessionRepository,
    task_repo: WorkflowTaskRepository,
    notif_repo: NotificationRepository,
    ws_id: str,
) -> None:
    """Emit a ``session_completed`` notification once every task is terminal.

    The notification is created at most once per session: if every task in the
    session is in a terminal state (and there is at least one task) and no
    ``session_completed`` notification exists yet for the session, one is created.
    Like :func:`_notify`, this is best-effort and never raises.

    Args:
        ws_repo: Repository used to resolve the session owner.
        task_repo: Repository used to read the session's tasks.
        notif_repo: Repository used to check for and persist the notification.
        ws_id: Primary key of the workflow session to evaluate.
    """
    try:
        tasks = await task_repo.list(limit=1000, offset=0, workflow_session_id=ws_id)
        if not tasks or any(t.status not in _TERMINAL_STATUSES for t in tasks):
            return
        if await notif_repo.exists_for_session(
            ws_id, NotificationType.session_completed
        ):
            return
    except Exception:
        logger.exception("failed to evaluate completion for workflow session %s", ws_id)
        return
    await _notify(
        ws_repo,
        notif_repo,
        ws_id,
        NotificationType.session_completed,
        "Workflow session completed",
        f"All {len(tasks)} task{'s' if len(tasks) != 1 else ''} "
        "in this workflow session have finished.",
    )


def _task_to_dict(task: WorkflowTaskRead) -> dict[str, Any]:
    """Convert a WorkflowTaskRead into a plain dict the LLM can consume."""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "depends_on_ids": list(task.depends_on_ids),
        "position": task.position,
        "tool_bindings": [
            {"server_id": b.mcp_server_id, "tool_name": b.tool_name}
            for b in task.tool_bindings
        ],
    }


def _parse_tool_bindings(raw: object) -> list[ToolBinding] | None:
    """Coerce ``[{"server_id", "tool_name"}, ...]`` into ToolBindings, or ``None``.

    Args:
        raw: The model-supplied tool list to validate.

    Returns:
        The parsed bindings, or ``None`` when ``raw`` is not a list of objects
        with non-empty string ``server_id`` and ``tool_name`` fields.
    """
    if not isinstance(raw, list):
        return None
    bindings: list[ToolBinding] = []
    for entry in raw:
        if not isinstance(entry, dict):
            return None
        server_id = entry.get("server_id")
        tool_name = entry.get("tool_name")
        if (
            not isinstance(server_id, str)
            or not server_id
            or not isinstance(tool_name, str)
            or not tool_name
        ):
            return None
        bindings.append(ToolBinding(mcp_server_id=server_id, tool_name=tool_name))
    return bindings


def _invalid_tools_error(label: str) -> dict[str, Any]:
    """Build the error payload for a malformed tools/tool_bindings argument."""
    return {
        "error": f"{label} must be a list of "
        '{"server_id": <registered MCP server id>, "tool_name": <tool name>} objects'
    }


def _parse_status(status: str | None) -> WorkflowTaskStatus | None:
    """Coerce a status string to a WorkflowTaskStatus, or ``None`` if invalid/absent."""
    if status is None:
        return None
    try:
        return WorkflowTaskStatus(status)
    except ValueError:
        return None


def _invalid_status_error(status: str) -> dict[str, Any]:
    """Build the error payload for an unrecognized status value."""
    valid = ", ".join(s.value for s in WorkflowTaskStatus)
    return {"error": f"invalid status {status!r}; must be one of: {valid}"}


def _not_in_session_error(task_id: str) -> dict[str, Any]:
    """Build the error payload for a task absent from the current session."""
    return {"error": f"WorkflowTask {task_id!r} not found in the current session"}


def _topo_sort(keys: list[str], by_key: dict[str, dict[str, Any]]) -> list[str] | None:
    """Return the batch keys in dependency order, or ``None`` if a cycle exists.

    Uses Kahn's algorithm, seeding the queue in the caller's original key order
    so the result is stable.

    Args:
        keys: The task keys in their declared order.
        by_key: Mapping of key to its task entry (whose ``depends_on`` lists
            other keys it depends on).

    Returns:
        A list of keys with every dependency preceding its dependents, or
        ``None`` if the dependency graph contains a cycle.
    """
    indegree: dict[str, int] = {k: 0 for k in keys}
    dependents: dict[str, list[str]] = {k: [] for k in keys}
    for key in keys:
        for dep in by_key[key].get("depends_on") or []:
            dependents[dep].append(key)
            indegree[key] += 1
    queue = [k for k in keys if indegree[k] == 0]
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in dependents[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return order if len(order) == len(keys) else None


async def register_workflow_tasks(
    tasks: list[dict[str, Any]], tool_context: ToolContext
) -> dict[str, Any]:
    """Register a plan of WorkflowTasks (a DAG) for the current session at once.

    Call this once, right after building the plan from the skill's steps. Each
    entry describes one task and may declare dependencies on other tasks *in the
    same batch* by their ``key``::

        {
          "key": "t1",                 # required, unique within this batch
          "title": "Gather sources",   # required
          "description": "...",        # optional
          "position": 0,               # optional layout/order hint
          "depends_on": ["t0"],        # optional, other entries' "key" values
          "tools": [                   # optional MCP tools this task will use
            {"server_id": "<registered MCP server id>", "tool_name": "<tool>"}
          ]
        }

    Tasks are created in dependency order; ``depends_on`` keys are resolved to the
    real task ids before edges are written, and every task starts as ``pending``.
    When ``position`` is omitted a task is positioned by its dependency order.
    ``tools`` binds MCP tools to the task: while the task is in progress those
    tools (and only those) can be invoked via ``call_mcp_tool``. Discover the
    available servers and tools with ``list_mcp_tools`` first, and only bind
    tools the task actually needs.

    Args:
        tasks: The plan entries described above.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"created": [{"key", "id", "title"}, ...]}``. On failure
        ``{"error": <message>}`` (unknown dependency key, duplicate key, cycle,
        missing title, or unresolved session); no tasks are created when the
        failure is detected before writing. If an unexpected repository error
        occurs mid-batch, the partial ``created`` list is also returned.
    """
    if not tasks:
        return {"error": "tasks must be a non-empty list"}

    by_key: dict[str, dict[str, Any]] = {}
    keys: list[str] = []
    for index, entry in enumerate(tasks):
        if not isinstance(entry, dict):
            return {"error": f"task at index {index} must be an object"}
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            return {"error": f"task at index {index} is missing a string 'key'"}
        if key in by_key:
            return {"error": f"duplicate task key {key!r}"}
        title = entry.get("title")
        if not isinstance(title, str) or not title:
            return {"error": f"task {key!r} is missing a string 'title'"}
        by_key[key] = entry
        keys.append(key)

    bindings_by_key: dict[str, list[ToolBinding]] = {}
    for key in keys:
        deps = by_key[key].get("depends_on") or []
        if not isinstance(deps, list):
            return {"error": f"task {key!r} 'depends_on' must be a list"}
        for dep in deps:
            if dep == key:
                return {"error": f"task {key!r} cannot depend on itself"}
            if dep not in by_key:
                return {"error": f"task {key!r} depends on unknown key {dep!r}"}
        bindings = _parse_tool_bindings(by_key[key].get("tools") or [])
        if bindings is None:
            return _invalid_tools_error(f"task {key!r} 'tools'")
        bindings_by_key[key] = bindings

    order = _topo_sort(keys, by_key)
    if order is None:
        return {"error": "tasks contain a dependency cycle"}

    async with _repos() as (ws_repo, task_repo, notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        user_id = _user_id(tool_context)
        key_to_id: dict[str, str] = {}
        created: list[dict[str, Any]] = []
        for position, key in enumerate(order):
            entry = by_key[key]
            dep_ids = [key_to_id[d] for d in (entry.get("depends_on") or [])]
            declared_position = entry.get("position")
            data = WorkflowTaskCreate(
                workflow_session_id=ws_id,
                title=entry["title"],
                description=entry.get("description"),
                position=declared_position
                if declared_position is not None
                else position,
                depends_on_ids=dep_ids,
                tool_bindings=bindings_by_key[key],
            )
            try:
                task = await task_repo.create(data, user_id=user_id)
            except (ForeignKeyViolationError, DependencyCycleError) as exc:
                return {
                    "error": f"failed to create task {key!r}: {exc}",
                    "created": created,
                }
            key_to_id[key] = task.id
            created.append({"key": key, "id": task.id, "title": task.title})
        count = len(created)
        await _notify(
            ws_repo,
            notif_repo,
            ws_id,
            NotificationType.approval_request,
            "Plan ready for approval",
            f"The agent registered a plan of {count} "
            f"task{'s' if count != 1 else ''} and is waiting for your approval.",
        )
        return {"created": created}


async def create_workflow_task(
    title: str,
    tool_context: ToolContext,
    description: str | None = None,
    depends_on_ids: list[str] | None = None,
    status: str | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a single WorkflowTask in the current session.

    Use this to add a task incrementally after the initial plan was registered.
    ``depends_on_ids`` must reference ids of tasks that already exist in the same
    session (use :func:`list_workflow_tasks` to find them).

    Args:
        title: The task title (required).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        description: Optional longer description.
        depends_on_ids: Optional ids of existing same-session tasks this task
            depends on.
        status: Optional initial status; defaults to ``pending``. One of
            "pending", "in_progress", "completed", "failed", "skipped".
        tool_bindings: Optional MCP tools to bind to the task, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``.
            Bound tools are the only MCP tools the task may invoke via
            ``call_mcp_tool`` while in progress.

    Returns:
        The created task dict, or ``{"error": <message>}`` on an invalid status,
        unknown dependency, unknown MCP server, cycle, or unresolved session.
    """
    status_enum = _parse_status(status)
    if status is not None and status_enum is None:
        return _invalid_status_error(status)
    bindings = _parse_tool_bindings(tool_bindings or [])
    if bindings is None:
        return _invalid_tools_error("tool_bindings")
    async with _repos() as (ws_repo, task_repo, _notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        data = WorkflowTaskCreate(
            workflow_session_id=ws_id,
            title=title,
            description=description,
            depends_on_ids=depends_on_ids or [],
            status=status_enum or WorkflowTaskStatus.pending,
            tool_bindings=bindings,
        )
        try:
            task = await task_repo.create(data, user_id=_user_id(tool_context))
        except (ForeignKeyViolationError, DependencyCycleError) as exc:
            return {"error": str(exc)}
        return _task_to_dict(task)


async def list_workflow_tasks(tool_context: ToolContext) -> dict[str, Any]:
    """List all WorkflowTasks in the current session, in position order.

    Call this to decide what to do next: pick a ``pending`` task whose
    ``depends_on_ids`` are all ``completed`` (a "runnable" task).

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"tasks": [{"id", "title", "description", "status", "depends_on_ids",
        "position"}, ...]}`` ordered by position then creation time, or
        ``{"error": <message>}`` if the session cannot be resolved.
    """
    async with _repos() as (ws_repo, task_repo, _notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        tasks = await task_repo.list(limit=1000, offset=0, workflow_session_id=ws_id)
        return {"tasks": [_task_to_dict(t) for t in tasks]}


async def get_workflow_task(task_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Fetch a single WorkflowTask from the current session.

    Args:
        task_id: Id of the task to fetch.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        The task dict, or ``{"error": <message>}`` if the session cannot be
        resolved or the task does not belong to it.
    """
    async with _repos() as (ws_repo, task_repo, _notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        task = await task_repo.get(task_id)
        if task is None or task.workflow_session_id != ws_id:
            return _not_in_session_error(task_id)
        return _task_to_dict(task)


async def update_workflow_task(
    task_id: str,
    tool_context: ToolContext,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    position: int | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Update fields of a WorkflowTask in the current session.

    Only the arguments you pass are changed. Use ``status`` to drive the
    lifecycle (``pending`` -> ``in_progress`` -> ``completed``/``failed``/
    ``skipped``): mark a task ``in_progress`` before working on it and
    ``completed``/``failed`` afterwards. Passing ``depends_on_ids`` replaces the
    task's full dependency set, letting you edit the DAG after creation;
    ``tool_bindings`` likewise replaces the task's full set of bound MCP tools.

    Args:
        task_id: Id of the task to update.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        title: New title, if changing.
        description: New description, if changing.
        status: New status, if changing. One of "pending", "in_progress",
            "completed", "failed", "skipped".
        position: New layout position, if changing.
        depends_on_ids: Replacement dependency ids (existing same-session tasks),
            if changing.
        tool_bindings: Replacement MCP tool bindings, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``,
            if changing.

    Returns:
        The updated task dict, or ``{"error": <message>}`` on an invalid status,
        unknown task, cross-session task, unknown dependency, unknown MCP
        server, cycle, or unresolved session.
    """
    status_enum = _parse_status(status)
    if status is not None and status_enum is None:
        return _invalid_status_error(status)
    bindings = (
        _parse_tool_bindings(tool_bindings) if tool_bindings is not None else None
    )
    if tool_bindings is not None and bindings is None:
        return _invalid_tools_error("tool_bindings")
    async with _repos() as (ws_repo, task_repo, notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        existing = await task_repo.get(task_id)
        if existing is None or existing.workflow_session_id != ws_id:
            return _not_in_session_error(task_id)
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if description is not None:
            fields["description"] = description
        if status_enum is not None:
            fields["status"] = status_enum
        if position is not None:
            fields["position"] = position
        if depends_on_ids is not None:
            fields["depends_on_ids"] = depends_on_ids
        if bindings is not None:
            fields["tool_bindings"] = bindings
        try:
            task = await task_repo.update(
                task_id, WorkflowTaskUpdate(**fields), user_id=_user_id(tool_context)
            )
        except NotFoundError:
            return _not_in_session_error(task_id)
        except (ForeignKeyViolationError, DependencyCycleError) as exc:
            return {"error": str(exc)}
        await _maybe_notify_session_completed(ws_repo, task_repo, notif_repo, ws_id)
        return _task_to_dict(task)


async def delete_workflow_task(
    task_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Delete a WorkflowTask from the current session.

    Args:
        task_id: Id of the task to delete.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"deleted": <task_id>}`` on success, or ``{"error": <message>}`` if the
        session cannot be resolved or the task does not belong to it.
    """
    async with _repos() as (ws_repo, task_repo, _notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        existing = await task_repo.get(task_id)
        if existing is None or existing.workflow_session_id != ws_id:
            return _not_in_session_error(task_id)
        await task_repo.delete(task_id)
        return {"deleted": task_id}
