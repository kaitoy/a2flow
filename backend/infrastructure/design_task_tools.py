"""ADK agent tools for managing a workflow's task templates from a design session.

These callables are attached to the design agents (see
:func:`infrastructure.agent.create_agent`) so the initial background run can
register the designed steps as WorkflowTaskTemplates and the interactive
design chat can refine it. They mirror
:mod:`infrastructure.workflow_task_tools`, with two differences: the tools
resolve the current run's :class:`models.design_session.DesignSession` (by
the ADK session id) and operate on the linked workflow's *templates*, and
templates carry no ``status`` — the lifecycle belongs to a run, not the design.

Like the session-task tools, every call opens its own ``AsyncSession`` on the
module-level engine (the tools run during an agent run, outside FastAPI's
per-request dependency-injection scope) and returns plain JSON-serializable
values, mapping repository errors to an ``{"error": ...}`` payload the agent
can react to instead of raising.

Every write here also settles the parent workflow's status through
:meth:`repositories.workflow.SqlWorkflowRepository.mark_design_edited`, exactly
like the REST edit surfaces in :mod:`services.workflow_task_template`. A
``published`` workflow moves to ``modified`` — task templates refined by chat
have drifted from the snapshot taken at publish time just as much as ones
edited through the admin UI, and runs keep using that snapshot until the
workflow is published again. A ``failed`` one recovers to ``draft``: this chat
is where a user repairs a design run that failed, and rebuilding the templates
is what repairs it. During the initial background generation run the workflow
is still ``generating``, so the call is a no-op there and needs no special
casing.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from google.adk.tools.tool_context import ToolContext
from pydantic import ValidationError
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
    DesignSessionRepository,
    SqlAgentSkillRepository,
    SqlDesignSessionRepository,
    SqlMCPServerRepository,
    SqlWorkflowRepository,
    SqlWorkflowTaskTemplateRepository,
    WorkflowRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)
from repositories.tenant_bootstrap import (
    NoTenantSessionError,
    resolve_design_session_tenant,
)

logger = logging.getLogger(__name__)

_NO_SESSION = (
    "no design session is bound to the current run; cannot manage task templates"
)

#: Hard cap on a title written by a design agent, enforced here rather than
#: taken from ``ShortText`` (200 chars, :mod:`models.constraints`) — that limit
#: guards the column, this one guards the *list UI*, where a title is rendered
#: as a chip beside every task depending on it and a long one is clipped to an
#: ellipsis. It matches the 30-character budget the agent's instructions ask for
#: (see ``_DESIGN_REGISTRATION_RULES`` in :mod:`infrastructure.agent`), so an
#: agent that follows them never trips it, and one that drifts into writing
#: sentences gets a correctable ``{"error": ...}`` back instead of quietly
#: filling the column.
#:
#: It binds only the agent tools. A human editing a template through the REST
#: API or the admin form is still held to ``ShortText`` alone.
_TITLE_MAX_LENGTH = 30


def _title_too_long_error(label: str, title: str) -> str:
    """Build the error message for a title over :data:`_TITLE_MAX_LENGTH`."""
    return (
        f"{label} title is {len(title)} characters, over the "
        f"{_TITLE_MAX_LENGTH} limit; use a terse imperative label of 2-4 words "
        f"({title[:_TITLE_MAX_LENGTH].rstrip()!r} is the budget) and move the "
        "detail into 'description'"
    )


@dataclass
class _Scope:
    """Per-tool-call resolved workflow id, tenant id, and scoped repositories."""

    workflow_id: str
    tenant_id: str
    ds_repo: DesignSessionRepository
    template_repo: WorkflowTaskTemplateRepository
    workflow_repo: WorkflowRepository

    async def mark_design_edited(self, tool_context: ToolContext) -> None:
        """Settle the templates' parent workflow status after a write.

        Called after every write so chat-refined templates record the same
        drift from the published snapshot that a REST edit does, and so a
        workflow left ``failed`` by its design run recovers once the user has
        rebuilt its templates through the chat. Any other status is left alone
        by the repository.

        Args:
            tool_context: The ADK tool context for the current invocation, read
                for the acting user id.
        """
        await self.workflow_repo.mark_design_edited(
            self.workflow_id, user_id=_user_id(tool_context)
        )


@asynccontextmanager
async def _repos(tool_context: ToolContext) -> AsyncIterator[_Scope]:
    """Open a database session and yield the resolved scope and its repositories.

    Opens a fresh ``AsyncSession`` on the module-level engine (the tools run
    outside FastAPI's request scope), resolves the current run's workflow id
    and tenant id, and wires a DesignSession repository, a
    WorkflowTaskTemplate repository, and the Workflow repository backing
    :meth:`_Scope.mark_design_edited` to it, all scoped to the resolved tenant.
    The engine is referenced through the ``database`` module so tests can
    monkeypatch ``database.engine``.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Yields:
        The resolved :class:`_Scope`.

    Raises:
        NoTenantSessionError: If no DesignSession is bound to the current run.
    """
    async with AsyncSession(database.engine) as db:
        session = getattr(tool_context, "session", None)
        session_id = getattr(session, "id", None)
        resolved = (
            await resolve_design_session_tenant(db, session_id) if session_id else None
        )
        if resolved is None:
            raise NoTenantSessionError()
        workflow_id, tenant_id = resolved
        workflow_repo = SqlWorkflowRepository(
            db,
            SqlAgentSkillRepository(db, tenant_id=tenant_id),
            tenant_id=tenant_id,
        )
        yield _Scope(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            ds_repo=SqlDesignSessionRepository(db, tenant_id=tenant_id),
            template_repo=SqlWorkflowTaskTemplateRepository(
                db,
                workflow_repo,
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            ),
            workflow_repo=workflow_repo,
        )


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


def _not_in_design_error(template_id: str) -> dict[str, Any]:
    """Build the error payload for a template absent from the current workflow's task templates."""
    return {
        "error": f"design task {template_id!r} not found in the current workflow's task templates"
    }


async def register_design_tasks(
    tasks: list[dict[str, Any]], tool_context: ToolContext
) -> dict[str, Any]:
    """Register a whole set of task templates (a DAG) for the current workflow at once.

    Call this once, right after designing the task templates from the skill's steps. Each
    entry describes one task and may declare dependencies on other tasks *in the
    same batch* by their ``key``::

        {
          "key": "t1",                 # required, unique within this batch
          "title": "Gather sources",   # required, 2-4 words, max 30 characters
          "description": "...",        # optional, where the detail belongs
          "position": 0,               # optional layout/order hint
          "depends_on": ["t0"],        # optional, other entries' "key" values
          "tools": [                   # optional MCP tools this task will use
            {"server_id": "<registered MCP server id>", "tool_name": "<tool>"}
          ]
        }

    A ``title`` is a terse imperative label, not a sentence: 2 to 4 words and at
    most 30 characters (e.g. "Gather sources", "Validate schema"), which is
    enforced — a longer one is rejected. It is listed as a chip next to every
    task that depends on it, so a long one is clipped. Anything that does not fit
    belongs in ``description``.

    Templates are created in dependency order; ``depends_on`` keys are resolved
    to the real template ids before edges are written. When ``position`` is
    omitted a template is positioned by its dependency order. ``tools`` binds
    MCP tools to the task: when the workflow is executed, the task copied from
    the template may invoke those tools (and only those) via ``call_mcp_tool``.
    Discover the available servers and tools with ``list_mcp_tools`` first, and
    only bind tools a task actually needs.

    Moves a ``published`` parent workflow to ``modified``.

    Args:
        tasks: The task-template entries described above.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"created": [{"key", "id", "title"}, ...]}``. On failure
        ``{"error": <message>}`` (unknown dependency key, duplicate key, cycle,
        missing or overlong title, or unresolved session); no templates are
        created when the failure is detected before writing. If an unexpected
        repository error occurs mid-batch, the partial ``created`` list is also
        returned.
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
        if len(title) > _TITLE_MAX_LENGTH:
            return {"error": _title_too_long_error(f"task {key!r}", title)}
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

    try:
        async with _repos(tool_context) as s:
            user_id = _user_id(tool_context)
            key_to_id: dict[str, str] = {}
            created: list[dict[str, Any]] = []
            for position, key in enumerate(order):
                entry = by_key[key]
                dep_ids = [key_to_id[d] for d in (entry.get("depends_on") or [])]
                declared_position = entry.get("position")
                try:
                    data = WorkflowTaskTemplateCreate(
                        workflow_id=s.workflow_id,
                        title=entry["title"],
                        description=entry.get("description"),
                        position=declared_position
                        if declared_position is not None
                        else position,
                        depends_on_ids=dep_ids,
                        tool_bindings=bindings_by_key[key],
                    )
                except ValidationError as exc:
                    # A field constraint the pre-checks above don't cover. Hand
                    # it back for the agent to fix rather than letting it escape
                    # the tool and fail the whole run.
                    if created:
                        await s.mark_design_edited(tool_context)
                    return {
                        "error": f"task {key!r} is invalid: {exc}",
                        "created": created,
                    }
                try:
                    template = await s.template_repo.create(data, user_id=user_id)
                except (ForeignKeyViolationError, DependencyCycleError) as exc:
                    if created:
                        await s.mark_design_edited(tool_context)
                    return {
                        "error": f"failed to create task {key!r}: {exc}",
                        "created": created,
                    }
                key_to_id[key] = template.id
                created.append({"key": key, "id": template.id, "title": template.title})
            # Once, after the batch: the first call already flips the status, so
            # per-template calls would only add redundant reads.
            await s.mark_design_edited(tool_context)
            return {"created": created}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def create_design_task(
    title: str,
    tool_context: ToolContext,
    description: str | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a single task template in the current workflow's task templates.

    Use this to add a task incrementally after the initial task templates were registered.
    ``depends_on_ids`` must reference ids of templates that already exist in the
    same workflow (use :func:`list_design_tasks` to find them).

    Moves a ``published`` parent workflow to ``modified``.

    Args:
        title: The task title (required). A terse imperative label, not a
            sentence: 2 to 4 words, at most 30 characters (e.g. "Gather
            sources") — a longer one is rejected. It is listed as a chip next to
            every task that depends on it, so a long one is clipped — put the
            detail in ``description``.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        description: Optional longer description.
        depends_on_ids: Optional ids of existing same-workflow templates this task
            depends on.
        tool_bindings: Optional MCP tools to bind to the task, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``.

    Returns:
        The created task dict, or ``{"error": <message>}`` on an unknown
        dependency, unknown MCP server, cycle, overlong title, or unresolved
        session.
    """

    bindings = _parse_tool_bindings(tool_bindings or [])
    if bindings is None:
        return _invalid_tools_error("tool_bindings")
    if len(title) > _TITLE_MAX_LENGTH:
        return {"error": _title_too_long_error("the", title)}
    try:
        async with _repos(tool_context) as s:
            data = WorkflowTaskTemplateCreate(
                workflow_id=s.workflow_id,
                title=title,
                description=description,
                depends_on_ids=depends_on_ids or [],
                tool_bindings=bindings,
            )
            template = await s.template_repo.create(
                data, user_id=_user_id(tool_context)
            )
            await s.mark_design_edited(tool_context)
            return _template_to_dict(template)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except (ForeignKeyViolationError, DependencyCycleError, ValidationError) as exc:
        return {"error": str(exc)}


async def list_design_tasks(tool_context: ToolContext) -> dict[str, Any]:
    """List all task templates of the current workflow, in position order.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"tasks": [{"id", "title", "description", "depends_on_ids",
        "position", "tool_bindings"}, ...]}`` ordered by position then creation
        time, or ``{"error": <message>}`` if the session cannot be resolved.
    """
    try:
        async with _repos(tool_context) as s:
            templates = await s.template_repo.list(
                limit=1000, offset=0, workflow_id=s.workflow_id
            )
            return {"tasks": [_template_to_dict(t) for t in templates]}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def get_design_task(
    template_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Fetch a single task template from the current workflow's task templates.

    Args:
        template_id: Id of the template to fetch.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        The task dict, or ``{"error": <message>}`` if the session cannot be
        resolved or the template does not belong to the workflow.
    """
    try:
        async with _repos(tool_context) as s:
            template = await s.template_repo.get(template_id)
            if template is None or template.workflow_id != s.workflow_id:
                return _not_in_design_error(template_id)
            return _template_to_dict(template)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def update_design_task(
    template_id: str,
    tool_context: ToolContext,
    title: str | None = None,
    description: str | None = None,
    position: int | None = None,
    depends_on_ids: list[str] | None = None,
    tool_bindings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Update fields of a task template in the current workflow's task templates.

    Only the arguments you pass are changed. Passing ``depends_on_ids`` replaces
    the template's full dependency set, letting you edit the DAG after creation;
    ``tool_bindings`` likewise replaces the template's full set of bound MCP
    tools.

    Moves a ``published`` parent workflow to ``modified``.

    Args:
        template_id: Id of the template to update.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        title: New title, if changing. A terse imperative label, not a sentence:
            2 to 4 words, at most 30 characters (e.g. "Gather sources") — a
            longer one is rejected. It is listed as a chip next to every task
            that depends on it, so a long one is clipped — put the detail in
            ``description``.
        description: New description, if changing.
        position: New layout position, if changing.
        depends_on_ids: Replacement dependency ids (existing same-workflow
            templates), if changing.
        tool_bindings: Replacement MCP tool bindings, each
            ``{"server_id": <registered MCP server id>, "tool_name": <tool>}``,
            if changing.

    Returns:
        The updated task dict, or ``{"error": <message>}`` on an unknown
        template, cross-workflow template, unknown dependency, unknown MCP server,
        cycle, overlong title, or unresolved session.
    """

    bindings = (
        _parse_tool_bindings(tool_bindings) if tool_bindings is not None else None
    )
    if tool_bindings is not None and bindings is None:
        return _invalid_tools_error("tool_bindings")
    if title is not None and len(title) > _TITLE_MAX_LENGTH:
        return {"error": _title_too_long_error("the new", title)}
    try:
        async with _repos(tool_context) as s:
            existing = await s.template_repo.get(template_id)
            if existing is None or existing.workflow_id != s.workflow_id:
                return _not_in_design_error(template_id)
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
                template = await s.template_repo.update(
                    template_id,
                    WorkflowTaskTemplateUpdate(**fields),
                    user_id=_user_id(tool_context),
                )
            except NotFoundError:
                return _not_in_design_error(template_id)
            await s.mark_design_edited(tool_context)
            return _template_to_dict(template)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except (ForeignKeyViolationError, DependencyCycleError, ValidationError) as exc:
        return {"error": str(exc)}


async def delete_design_task(
    template_id: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Delete a task template from the current workflow's task templates.

    Moves a ``published`` parent workflow to ``modified``.

    Args:
        template_id: Id of the template to delete.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"deleted": <template_id>}`` on success, or ``{"error": <message>}``
        if the session cannot be resolved or the template does not belong to
        the workflow.
    """
    try:
        async with _repos(tool_context) as s:
            existing = await s.template_repo.get(template_id)
            if existing is None or existing.workflow_id != s.workflow_id:
                return _not_in_design_error(template_id)
            await s.template_repo.delete(template_id)
            await s.mark_design_edited(tool_context)
            return {"deleted": template_id}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
