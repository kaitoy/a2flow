"""ADK agent tools for managing the current workflow execution's WorkflowTasks.

These callables are attached to the skill-driven execution agent (see
:func:`infrastructure.agent.create_agent`) so it can iterate the run's tasks —
copied from the workflow's published templates at execute time — updating
their status as it works, and adjust the task list mid-run when needed. Bulk template
registration lives in :mod:`infrastructure.design_task_tools`, which the
design agents use to write the workflow's templates.

Two facts shape the implementation:

* The tools run *during* the AG-UI SSE stream, outside FastAPI's per-request
  dependency-injection scope, so each call opens its own ``AsyncSession`` on the
  module-level engine rather than receiving an injected session.
* A single ``ADKAgent`` is cached per skill and serves every session that uses
  that skill, so the tools cannot capture a specific ``workflow_execution_id`` at
  agent-creation time. Instead they resolve it at call time by mapping the ADK
  session id (the AG-UI thread id, stored on ``WorkflowExecution.session_id``)
  back to the WorkflowExecution primary key and tenant via
  :func:`repositories.tenant_bootstrap.resolve_workflow_execution_tenant` -- the
  tenant is needed to construct every repository below, since enforcement is
  applied explicitly in the repository layer rather than through a
  request-scoped mechanism these out-of-request tool calls never pass through.

Every tool returns plain JSON-serializable values (``dict``/``list``) so the LLM
can consume them, mapping repository errors to an ``{"error": ...}`` payload the
agent can react to instead of raising.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from models.notification import NotificationCreate, NotificationType
from models.workflow_task import (
    TaskErrorKind,
    ToolBinding,
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskStatus,
    WorkflowTaskUpdate,
)
from repositories import (
    SqlMCPServerRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
    WorkflowExecutionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)
from repositories.tenant_bootstrap import (
    NoTenantSessionError,
    resolve_workflow_execution_tenant,
)

if TYPE_CHECKING:
    # Type-only: importing any ``services`` submodule at runtime executes
    # ``services/__init__``, which pulls in ``services.workflow_execution`` ->
    # ``infrastructure.agent`` -> this module, a cycle at import time. The
    # runtime import is deferred into :func:`_scope`, the same way
    # :func:`_evaluate_completion` defers its own.
    from services.notification_dispatch import NotificationDispatcher

logger = logging.getLogger(__name__)

_NO_SESSION = "no workflow execution is bound to the current run; cannot manage tasks"

#: ``RunAgentInput.state`` key carrying the effective (impersonation-aware)
#: caller actually driving the current turn, stamped in by
#: ``infrastructure.agent.with_user_id`` -- as opposed to the ADK session's
#: ``user_id``, which stays pinned to a shared session's fixed owner (an
#: execution's initiator, or a workflow's design-session creator) for the
#: session's whole life. The ``temp:`` prefix
#: (``google.adk.sessions.state.State.TEMP_PREFIX``) makes ag-ui-adk keep it
#: out of the session's persisted state, so it never leaks into another
#: participant's later turn on the same shared session. Read by :func:`_user_id`
#: below, and (via that helper) by every write tool in this module and in
#: ``approval_tools.py``/``design_task_tools.py``.
ACTING_USER_STATE_KEY = "temp:actingUserId"


@dataclass
class _Scope:
    """Per-tool-call resolved WorkflowExecution id, tenant id, and scoped repos."""

    execution_id: str
    tenant_id: str
    execution_repo: WorkflowExecutionRepository
    task_repo: WorkflowTaskRepository
    # Quoted so the dataclass does not evaluate the name at class-creation
    # time -- it only exists under TYPE_CHECKING (see the import above).
    notifications: "NotificationDispatcher"


async def _resolve_scope(
    tool_context: ToolContext, db: AsyncSession
) -> tuple[str, str]:
    """Resolve the current run's ``(workflow_execution_id, tenant_id)``.

    Reads the ADK session id from ``tool_context.session.id`` and maps it to
    the owning WorkflowExecution's primary key and tenant -- the foreign key
    target for WorkflowTask records, and the trust anchor every repository
    built for this call is scoped to.

    Args:
        tool_context: The ADK tool context for the current invocation.
        db: The database session to resolve against.

    Returns:
        A ``(workflow_execution_id, tenant_id)`` tuple.

    Raises:
        NoTenantSessionError: If the session id is missing or no
            WorkflowExecution matches it.
    """
    session = getattr(tool_context, "session", None)
    session_id = getattr(session, "id", None)
    resolved = (
        await resolve_workflow_execution_tenant(db, session_id) if session_id else None
    )
    if resolved is None:
        raise NoTenantSessionError()
    return resolved


@asynccontextmanager
async def _repos(tool_context: ToolContext) -> AsyncIterator[_Scope]:
    """Open a database session and yield the resolved scope and its repositories.

    Opens a fresh ``AsyncSession`` on the module-level engine (the tools run
    outside FastAPI's request scope), resolves the current run's
    WorkflowExecution id and tenant id, and wires a WorkflowExecution repository, a
    WorkflowTask repository, and a notification dispatcher to it, all scoped
    to the resolved tenant. The engine is referenced through the ``database``
    module so tests can monkeypatch ``database.engine``.

    The dispatcher's import is deferred to call time for the same reason
    :func:`_evaluate_completion` defers its own: reaching into ``services`` at
    module import time closes a cycle back through ``infrastructure.agent``.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Yields:
        The resolved :class:`_Scope`.

    Raises:
        NoTenantSessionError: If no WorkflowExecution is bound to the current run.
    """
    from services.notification_dispatch import build_notification_dispatcher

    async with AsyncSession(database.engine) as db:
        execution_id, tenant_id = await _resolve_scope(tool_context, db)
        execution_repo = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
        yield _Scope(
            execution_id=execution_id,
            tenant_id=tenant_id,
            execution_repo=execution_repo,
            task_repo=SqlWorkflowTaskRepository(
                db,
                execution_repo,
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            ),
            notifications=build_notification_dispatcher(db, tenant_id=tenant_id),
        )


def _user_id(tool_context: ToolContext) -> str:
    """Return the acting caller's user id for audit fields.

    Prefers the per-turn acting user stamped into session state by the router
    (see :data:`ACTING_USER_STATE_KEY`) -- impersonation-aware, since it comes
    from ``CurrentUserDep`` -- falling back to the ADK session's fixed owner id
    (``tool_context.user_id``) when absent, e.g. the unattended initial-design
    background run, which never goes through ``with_user_id``'s
    ``acting_user_id`` parameter. Defaults to ``"user"`` if neither is set.
    """
    state = getattr(tool_context, "state", None)
    acting = state.get(ACTING_USER_STATE_KEY) if state is not None else None
    if acting:
        return str(acting)
    return getattr(tool_context, "user_id", None) or "user"


async def _notify(
    execution_repo: WorkflowExecutionRepository,
    notifications: "NotificationDispatcher",
    execution_id: str,
    notification_type: NotificationType,
    title: str,
    body: str | None = None,
    recipient: str | None = None,
) -> None:
    """Create a notification addressed to ``recipient`` (default: the execution initiator).

    When ``recipient`` is omitted the notification is addressed to the session's
    ``created_by`` (the real user who started the session); pass ``recipient`` to
    target a different user, such as an approval request's designated approver.
    The audit user is always the session's ``created_by``, which keeps the
    ``created_by`` foreign key valid even though the tool's own ``tool_context``
    user id may be a placeholder. Notification creation is best-effort: any failure
    is logged and swallowed so a notification problem never breaks the task
    operation that triggered it.

    Args:
        execution_repo: Repository used to resolve the session and its owner.
        notifications: Dispatcher that persists the notification and, when a
            relay is configured, emails it to the recipient.
        execution_id: Primary key of the workflow execution the notification concerns.
        notification_type: The kind of event being announced.
        title: Short headline shown in the notification panel.
        body: Optional longer description.
        recipient: User id to address the notification to; defaults to the
            execution initiator when ``None``.
    """
    try:
        execution = await execution_repo.get(execution_id)
        if execution is None:
            return
        data = NotificationCreate(
            user_id=recipient or execution.created_by,
            type=notification_type,
            title=title,
            body=body,
            workflow_execution_id=execution_id,
        )
        await notifications.create(data, user_id=execution.created_by)
    except Exception:
        logger.exception(
            "failed to create %s notification for workflow execution %s",
            notification_type,
            execution_id,
        )


async def _evaluate_completion(scope: _Scope) -> None:
    """Re-run the shared run-completion bookkeeping after a task write.

    The import is deferred to call time on purpose. ``evaluate_completion``
    lives in the service layer, where the rule belongs, and importing any
    ``services`` submodule executes ``services/__init__``, which pulls in
    ``services.workflow_execution`` -> ``infrastructure.agent`` -> this module:
    a cycle at import time. Resolving it here, once the modules are loaded,
    keeps the rule in its proper layer instead of duplicating it down here.

    Args:
        scope: The current tool call's resolved run and repositories.
    """
    from services.workflow_execution_completion import evaluate_completion

    await evaluate_completion(
        executions=scope.execution_repo,
        tasks=scope.task_repo,
        notifications=scope.notifications,
        execution_id=scope.execution_id,
    )


def _task_to_dict(task: WorkflowTaskRead) -> dict[str, Any]:
    """Convert a WorkflowTaskRead into a plain dict the LLM can consume."""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "error_kind": task.error_kind.value if task.error_kind else None,
        "error_message": task.error_message,
        "depends_on_ids": list(task.depends_on_ids),
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


def _parse_error_kind(error_kind: str | None) -> TaskErrorKind | None:
    """Coerce a failure-cause string to a TaskErrorKind, or ``None`` if invalid/absent."""
    if error_kind is None:
        return None
    try:
        return TaskErrorKind(error_kind)
    except ValueError:
        return None


def _invalid_error_kind_error(error_kind: str) -> dict[str, Any]:
    """Build the error payload for an unrecognized error_kind value."""
    valid = ", ".join(k.value for k in TaskErrorKind)
    return {"error": f"invalid error_kind {error_kind!r}; must be one of: {valid}"}


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


async def create_workflow_task(
    title: str,
    tool_context: ToolContext,
    description: str | None = None,
    depends_on_ids: list[str] | None = None,
    status: str | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a single WorkflowTask in the current session.

    Use this to add a task incrementally after the initial task templates were registered.
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
    try:
        async with _repos(tool_context) as s:
            data = WorkflowTaskCreate(
                workflow_execution_id=s.execution_id,
                title=title,
                description=description,
                depends_on_ids=depends_on_ids or [],
                status=status_enum or WorkflowTaskStatus.pending,
                tool_bindings=bindings,
            )
            task = await s.task_repo.create(data, user_id=_user_id(tool_context))
            return _task_to_dict(task)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except (ForeignKeyViolationError, DependencyCycleError) as exc:
        return {"error": str(exc)}


async def list_workflow_tasks(tool_context: ToolContext) -> dict[str, Any]:
    """List all WorkflowTasks in the current session, in creation order.

    Call this to decide what to do next: pick a ``pending`` task whose
    ``depends_on_ids`` are all ``completed`` (a "runnable" task). When several
    are runnable, the one appearing first in this list was created first.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"tasks": [{"id", "title", "description", "status", "depends_on_ids",
        "tool_bindings"}, ...]}`` ordered by creation time, or
        ``{"error": <message>}`` if the session cannot be resolved.
    """
    try:
        async with _repos(tool_context) as s:
            tasks = await s.task_repo.list(
                limit=1000, offset=0, workflow_execution_id=s.execution_id
            )
            return {"tasks": [_task_to_dict(t) for t in tasks]}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


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
    try:
        async with _repos(tool_context) as s:
            task = await s.task_repo.get(task_id)
            if task is None or task.workflow_execution_id != s.execution_id:
                return _not_in_session_error(task_id)
            return _task_to_dict(task)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def update_workflow_task(
    task_id: str,
    tool_context: ToolContext,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    error_kind: str | None = None,
    error_message: str | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Update fields of a WorkflowTask in the current session.

    Only the arguments you pass are changed. Use ``status`` to drive the
    lifecycle (``pending`` -> ``in_progress`` -> ``completed``/``failed``/
    ``skipped``): mark a task ``in_progress`` before working on it and
    ``completed``/``failed`` afterwards. Whenever you set ``status`` to
    "failed", also pass ``error_kind`` and ``error_message`` so the failure can
    be triaged later. Passing ``depends_on_ids`` replaces the task's full
    dependency set, letting you edit the DAG after creation; ``tool_bindings``
    likewise replaces the task's full set of bound MCP tools.

    Args:
        task_id: Id of the task to update.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        title: New title, if changing.
        description: New description, if changing.
        status: New status, if changing. One of "pending", "in_progress",
            "completed", "failed", "skipped".
        error_kind: Why the task failed. Set this together with
            ``status="failed"``. Must be exactly one of these seven values:
            "api_error" (an external API or MCP tool returned an error
            response), "timeout" (a call did not return within its time limit),
            "script_error" (the skill's own code raised an unhandled
            exception), "invalid_input" (the data the task was given was
            malformed or incomplete), "permission_denied" (you lacked the
            credentials or authorization to proceed), "rejected" (a human
            rejected the task's approval request), or "other" (none of the
            above — explain in ``error_message``).
        error_message: One-sentence description of the failure, up to 200
            characters. Include the concrete detail ``error_kind`` cannot carry,
            such as the tool or endpoint that failed and what it reported.
        depends_on_ids: Replacement dependency ids (existing same-session tasks),
            if changing.
        tool_bindings: Replacement MCP tool bindings, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``,
            if changing.

    Returns:
        The updated task dict, or ``{"error": <message>}`` on an invalid status
        or error kind, unknown task, cross-session task, unknown dependency,
        unknown MCP server, cycle, or unresolved session.
    """
    status_enum = _parse_status(status)
    if status is not None and status_enum is None:
        return _invalid_status_error(status)
    error_kind_enum = _parse_error_kind(error_kind)
    if error_kind is not None and error_kind_enum is None:
        return _invalid_error_kind_error(error_kind)
    bindings = (
        _parse_tool_bindings(tool_bindings) if tool_bindings is not None else None
    )
    if tool_bindings is not None and bindings is None:
        return _invalid_tools_error("tool_bindings")
    try:
        async with _repos(tool_context) as s:
            existing = await s.task_repo.get(task_id)
            if existing is None or existing.workflow_execution_id != s.execution_id:
                return _not_in_session_error(task_id)
            fields: dict[str, Any] = {}
            if title is not None:
                fields["title"] = title
            if description is not None:
                fields["description"] = description
            if status_enum is not None:
                fields["status"] = status_enum
            if error_kind_enum is not None:
                fields["error_kind"] = error_kind_enum
            if error_message is not None:
                fields["error_message"] = error_message
            if depends_on_ids is not None:
                fields["depends_on_ids"] = depends_on_ids
            if bindings is not None:
                fields["tool_bindings"] = bindings
            try:
                task = await s.task_repo.update(
                    task_id,
                    WorkflowTaskUpdate(**fields),
                    user_id=_user_id(tool_context),
                )
            except NotFoundError:
                return _not_in_session_error(task_id)
            await _evaluate_completion(s)
            return _task_to_dict(task)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except (ForeignKeyViolationError, DependencyCycleError) as exc:
        return {"error": str(exc)}


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
    try:
        async with _repos(tool_context) as s:
            existing = await s.task_repo.get(task_id)
            if existing is None or existing.workflow_execution_id != s.execution_id:
                return _not_in_session_error(task_id)
            await s.task_repo.delete(task_id)
            return {"deleted": task_id}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
