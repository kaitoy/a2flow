"""ADK agent tools for managing a workflow's task templates from a planning session.

These callables are attached to the planning agents (see
:func:`infrastructure.agent.create_agent`) so the initial background run can
register the generated plan as WorkflowTaskTemplates and the interactive
planning chat can refine it. They mirror
:mod:`infrastructure.workflow_task_tools`, with two differences: the tools
resolve the current run's :class:`models.planning_session.PlanningSession` (by
the ADK session id) and operate on the linked workflow's *templates*, and
templates carry no ``status`` — the lifecycle belongs to a run, not the plan.

Like the session-task tools, every call opens its own ``AsyncSession`` on the
module-level engine (the tools run during an agent run, outside FastAPI's
per-request dependency-injection scope) and returns plain JSON-serializable
values, mapping repository errors to an ``{"error": ...}`` payload the agent
can react to instead of raising.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.workflow_task_tools import (
    _invalid_tools_error,
    _parse_tool_bindings,
    _topo_sort,
    _user_id,
)
from models.workflow_task import ToolBinding
from models.workflow_task_template import (
    WorkflowTaskTemplateCreate,
    WorkflowTaskTemplateRead,
    WorkflowTaskTemplateUpdate,
)
from repositories import (
    PlanningSessionRepository,
    SqlAgentSkillRepository,
    SqlMCPServerRepository,
    SqlPlanningSessionRepository,
    SqlWorkflowRepository,
    SqlWorkflowTaskTemplateRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

_NO_SESSION = (
    "no planning session is bound to the current run; cannot manage task templates"
)


@asynccontextmanager
async def _repos() -> AsyncIterator[
    tuple[PlanningSessionRepository, WorkflowTaskTemplateRepository]
]:
    """Open a database session and yield the planning-session and template repos.

    Opens a fresh ``AsyncSession`` on the module-level engine (the tools run
    outside FastAPI's request scope) and wires a PlanningSession repository and
    a WorkflowTaskTemplate repository to it. The engine is referenced through
    the ``database`` module so tests can monkeypatch ``database.engine``.

    Yields:
        A ``(planning_session_repository, workflow_task_template_repository)``
        tuple bound to the same session.
    """
    async with AsyncSession(database.engine) as db:
        yield (
            SqlPlanningSessionRepository(db),
            SqlWorkflowTaskTemplateRepository(
                db,
                SqlWorkflowRepository(db, SqlAgentSkillRepository(db)),
                SqlMCPServerRepository(db),
            ),
        )


async def _resolve_workflow_id(
    tool_context: ToolContext, ps_repo: PlanningSessionRepository
) -> str | None:
    """Resolve the workflow whose templates the current run edits, or ``None``.

    Reads the ADK session id from ``tool_context.session.id`` and maps it to the
    owning PlanningSession, whose ``workflow_id`` is the foreign key target for
    WorkflowTaskTemplate records.

    Args:
        tool_context: The ADK tool context for the current invocation.
        ps_repo: Repository used to look the session up by its ADK session id.

    Returns:
        The workflow's primary key, or ``None`` if the session id is missing or
        no PlanningSession matches it.
    """
    session = getattr(tool_context, "session", None)
    session_id = getattr(session, "id", None)
    if not session_id:
        return None
    ps = await ps_repo.get_by_session_id(session_id)
    return ps.workflow_id if ps is not None else None


def _template_to_dict(template: WorkflowTaskTemplateRead) -> dict[str, Any]:
    """Convert a WorkflowTaskTemplateRead into a plain dict the LLM can consume."""
    return {
        "id": template.id,
        "title": template.title,
        "description": template.description,
        "depends_on_ids": list(template.depends_on_ids),
        "position": template.position,
        "tool_bindings": [
            {"server_id": b.mcp_server_id, "tool_name": b.tool_name}
            for b in template.tool_bindings
        ],
    }


def _not_in_plan_error(template_id: str) -> dict[str, Any]:
    """Build the error payload for a template absent from the current workflow's plan."""
    return {
        "error": f"planning task {template_id!r} not found in the current workflow's plan"
    }


async def register_planning_tasks(
    tasks: list[dict[str, Any]], tool_context: ToolContext
) -> dict[str, Any]:
    """Register a plan of task templates (a DAG) for the current workflow at once.

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

    Templates are created in dependency order; ``depends_on`` keys are resolved
    to the real template ids before edges are written. When ``position`` is
    omitted a template is positioned by its dependency order. ``tools`` binds
    MCP tools to the task: when the workflow is executed, the task copied from
    the template may invoke those tools (and only those) via ``call_mcp_tool``.
    Discover the available servers and tools with ``list_mcp_tools`` first, and
    only bind tools a task actually needs.

    Args:
        tasks: The plan entries described above.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"created": [{"key", "id", "title"}, ...]}``. On failure
        ``{"error": <message>}`` (unknown dependency key, duplicate key, cycle,
        missing title, or unresolved session); no templates are created when the
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

    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        user_id = _user_id(tool_context)
        key_to_id: dict[str, str] = {}
        created: list[dict[str, Any]] = []
        for position, key in enumerate(order):
            entry = by_key[key]
            dep_ids = [key_to_id[d] for d in (entry.get("depends_on") or [])]
            declared_position = entry.get("position")
            data = WorkflowTaskTemplateCreate(
                workflow_id=workflow_id,
                title=entry["title"],
                description=entry.get("description"),
                position=declared_position
                if declared_position is not None
                else position,
                depends_on_ids=dep_ids,
                tool_bindings=bindings_by_key[key],
            )
            try:
                template = await template_repo.create(data, user_id=user_id)
            except (ForeignKeyViolationError, DependencyCycleError) as exc:
                return {
                    "error": f"failed to create task {key!r}: {exc}",
                    "created": created,
                }
            key_to_id[key] = template.id
            created.append({"key": key, "id": template.id, "title": template.title})
        return {"created": created}


async def create_planning_task(
    title: str,
    tool_context: ToolContext,
    description: str | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a single task template in the current workflow's plan.

    Use this to add a task incrementally after the initial plan was registered.
    ``depends_on_ids`` must reference ids of templates that already exist in the
    same plan (use :func:`list_planning_tasks` to find them).

    Args:
        title: The task title (required).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        description: Optional longer description.
        depends_on_ids: Optional ids of existing same-plan templates this task
            depends on.
        tool_bindings: Optional MCP tools to bind to the task, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``.

    Returns:
        The created task dict, or ``{"error": <message>}`` on an unknown
        dependency, unknown MCP server, cycle, or unresolved session.
    """

    bindings = _parse_tool_bindings(tool_bindings or [])
    if bindings is None:
        return _invalid_tools_error("tool_bindings")
    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        data = WorkflowTaskTemplateCreate(
            workflow_id=workflow_id,
            title=title,
            description=description,
            depends_on_ids=depends_on_ids or [],
            tool_bindings=bindings,
        )
        try:
            template = await template_repo.create(data, user_id=_user_id(tool_context))
        except (ForeignKeyViolationError, DependencyCycleError) as exc:
            return {"error": str(exc)}
        return _template_to_dict(template)


async def list_planning_tasks(tool_context: ToolContext) -> dict[str, Any]:
    """List all task templates of the current workflow's plan, in position order.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"tasks": [{"id", "title", "description", "depends_on_ids",
        "position", "tool_bindings"}, ...]}`` ordered by position then creation
        time, or ``{"error": <message>}`` if the session cannot be resolved.
    """
    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        templates = await template_repo.list(
            limit=1000, offset=0, workflow_id=workflow_id
        )
        return {"tasks": [_template_to_dict(t) for t in templates]}


async def get_planning_task(
    template_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Fetch a single task template from the current workflow's plan.

    Args:
        template_id: Id of the template to fetch.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        The task dict, or ``{"error": <message>}`` if the session cannot be
        resolved or the template does not belong to the plan.
    """
    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        template = await template_repo.get(template_id)
        if template is None or template.workflow_id != workflow_id:
            return _not_in_plan_error(template_id)
        return _template_to_dict(template)


async def update_planning_task(
    template_id: str,
    tool_context: ToolContext,
    title: str | None = None,
    description: str | None = None,
    position: int | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Update fields of a task template in the current workflow's plan.

    Only the arguments you pass are changed. Passing ``depends_on_ids`` replaces
    the template's full dependency set, letting you edit the DAG after creation;
    ``tool_bindings`` likewise replaces the template's full set of bound MCP
    tools.

    Args:
        template_id: Id of the template to update.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        title: New title, if changing.
        description: New description, if changing.
        position: New layout position, if changing.
        depends_on_ids: Replacement dependency ids (existing same-plan
            templates), if changing.
        tool_bindings: Replacement MCP tool bindings, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``,
            if changing.

    Returns:
        The updated task dict, or ``{"error": <message>}`` on an unknown
        template, cross-plan template, unknown dependency, unknown MCP server,
        cycle, or unresolved session.
    """

    bindings = (
        _parse_tool_bindings(tool_bindings) if tool_bindings is not None else None
    )
    if tool_bindings is not None and bindings is None:
        return _invalid_tools_error("tool_bindings")
    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        existing = await template_repo.get(template_id)
        if existing is None or existing.workflow_id != workflow_id:
            return _not_in_plan_error(template_id)
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if description is not None:
            fields["description"] = description
        if position is not None:
            fields["position"] = position
        if depends_on_ids is not None:
            fields["depends_on_ids"] = depends_on_ids
        if bindings is not None:
            fields["tool_bindings"] = bindings
        try:
            template = await template_repo.update(
                template_id,
                WorkflowTaskTemplateUpdate(**fields),
                user_id=_user_id(tool_context),
            )
        except NotFoundError:
            return _not_in_plan_error(template_id)
        except (ForeignKeyViolationError, DependencyCycleError) as exc:
            return {"error": str(exc)}
        return _template_to_dict(template)


async def delete_planning_task(
    template_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Delete a task template from the current workflow's plan.

    Args:
        template_id: Id of the template to delete.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"deleted": <template_id>}`` on success, or ``{"error": <message>}``
        if the session cannot be resolved or the template does not belong to
        the plan.
    """
    async with _repos() as (ps_repo, template_repo):
        workflow_id = await _resolve_workflow_id(tool_context, ps_repo)
        if workflow_id is None:
            return {"error": _NO_SESSION}
        existing = await template_repo.get(template_id)
        if existing is None or existing.workflow_id != workflow_id:
            return _not_in_plan_error(template_id)
        await template_repo.delete(template_id)
        return {"deleted": template_id}
