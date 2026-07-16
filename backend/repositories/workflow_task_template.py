"""WorkflowTaskTemplate repository: Protocol interface and SQLModel-backed implementation.

Templates form a directed acyclic graph (DAG): each template may depend on zero
or more other templates of the same workflow. Dependency edges are persisted in
the ``workflow_task_template_dependencies`` join table and exposed on
:class:`WorkflowTaskTemplateRead` as ``depends_on_ids``. The repository enforces
the same invariants as the session-task repository whenever edges are written:
every dependency target must exist and belong to the same workflow, a template
may not depend on itself, and the resulting edge set must remain acyclic.

Templates may additionally bind MCP tools (a registered server plus a tool
name). Bindings are persisted in the ``workflow_task_template_tool_bindings``
join table and exposed on :class:`WorkflowTaskTemplateRead` as
``tool_bindings``; every bound server must exist when bindings are written.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_task import ToolBinding
from models.workflow_task_template import (
    WorkflowTaskTemplate,
    WorkflowTaskTemplateCreate,
    WorkflowTaskTemplateDependency,
    WorkflowTaskTemplateRead,
    WorkflowTaskTemplateToolBinding,
    WorkflowTaskTemplateUpdate,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)
from repositories.mcp_server import MCPServerRepository
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.workflow import WorkflowRepository
from repositories.workflow_task import _dedupe, _dedupe_bindings, _sorted_bindings

# Module-level aliases for ``list[...]`` types. The repository defines a method
# named ``list``, which causes mypy to resolve a bare ``list[...]`` annotation in
# methods declared after it to that method rather than the builtin; the aliases
# are evaluated in module scope where ``list`` is unambiguously the builtin.
_StrList = list[str]
_BindingList = list[ToolBinding]


class WorkflowTaskTemplateRepository(Protocol):
    """Interface for WorkflowTaskTemplate persistence operations."""

    async def get(self, template_id: str) -> WorkflowTaskTemplateRead | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_id: str | None = None,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowTaskTemplateRead]: ...

    async def create(
        self, data: WorkflowTaskTemplateCreate, *, user_id: str
    ) -> WorkflowTaskTemplateRead: ...

    async def update(
        self, template_id: str, data: WorkflowTaskTemplateUpdate, *, user_id: str
    ) -> WorkflowTaskTemplateRead: ...

    async def delete(self, template_id: str) -> None: ...


class SqlWorkflowTaskTemplateRepository:
    """SQLModel-backed implementation of WorkflowTaskTemplateRepository.

    Validates that the referenced ``workflow_id`` exists before creating a
    template, raising ForeignKeyViolationError if it does not. Dependency edges
    are validated for existence, same-workflow membership, self-loops, and
    acyclicity before being written; reads resolve a template's outgoing edges
    into ``depends_on_ids``. Tool bindings are validated against the registered
    MCP servers before being written; reads resolve them into ``tool_bindings``.
    """

    def __init__(
        self,
        session: AsyncSession,
        workflows: WorkflowRepository,
        mcp_repo: MCPServerRepository,
    ) -> None:
        """Store the session and the Workflow/MCPServer repos for FK checks."""
        self._db = session
        self._workflows = workflows
        self._mcp = mcp_repo

    async def get(self, template_id: str) -> WorkflowTaskTemplateRead | None:
        """Return the template with the given ID resolved into a read model, or ``None``."""
        template = await self._db.get(WorkflowTaskTemplate, template_id)
        if template is None:
            return None
        return self._to_read(
            template,
            await self._deps_for(template_id),
            await self._bindings_for(template_id),
        )

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_id: str | None = None,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowTaskTemplateRead]:
        """Return templates, defaulting to ``position`` then ``created_at`` order.

        When ``workflow_id`` is supplied, only templates belonging to that
        workflow are returned. Each template's outgoing dependency edges are
        resolved into ``depends_on_ids`` with a single batched query.
        """
        stmt = select(WorkflowTaskTemplate)
        if workflow_id is not None:
            stmt = stmt.where(WorkflowTaskTemplate.workflow_id == workflow_id)
        stmt = apply_filters(stmt, WorkflowTaskTemplate, filters)
        stmt = apply_sort(
            stmt,
            WorkflowTaskTemplate,
            sort,
            default=[
                col(WorkflowTaskTemplate.position).asc(),
                col(WorkflowTaskTemplate.created_at).asc(),
            ],
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        templates = list(result.all())
        deps = await self._deps_for_many([t.id for t in templates])
        bindings = await self._bindings_for_many([t.id for t in templates])
        return [
            self._to_read(t, deps.get(t.id, []), bindings.get(t.id, []))
            for t in templates
        ]

    async def create(
        self, data: WorkflowTaskTemplateCreate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Create a new template after validating the parent workflow, dependencies, and tool bindings."""
        if await self._workflows.get(data.workflow_id) is None:
            raise ForeignKeyViolationError("Workflow", data.workflow_id)
        template = WorkflowTaskTemplate.model_validate(
            {
                **data.model_dump(exclude={"depends_on_ids", "tool_bindings"}),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        dep_ids = _dedupe(data.depends_on_ids or [])
        await self._validate_dependencies(template.id, data.workflow_id, dep_ids)
        bindings = _dedupe_bindings(data.tool_bindings or [])
        await self._validate_bindings(bindings)
        self._db.add(template)
        for dep_id in dep_ids:
            self._db.add(
                WorkflowTaskTemplateDependency(
                    template_id=template.id, depends_on_id=dep_id
                )
            )
        for binding in bindings:
            self._db.add(
                WorkflowTaskTemplateToolBinding(
                    template_id=template.id,
                    mcp_server_id=binding.mcp_server_id,
                    tool_name=binding.tool_name,
                )
            )
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(template)
        return self._to_read(template, sorted(dep_ids), _sorted_bindings(bindings))

    async def update(
        self, template_id: str, data: WorkflowTaskTemplateUpdate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Apply a partial update to an existing template.

        When ``data.depends_on_ids`` is ``None`` the template's edges are left
        unchanged; when it is a list the full set of outgoing edges is replaced
        after validation. ``data.tool_bindings`` follows the same semantics for
        the template's bound MCP tools. ``workflow_id`` is not part of
        ``WorkflowTaskTemplateUpdate`` so no parent re-validation is needed here.
        """
        template = await self._db.get(WorkflowTaskTemplate, template_id)
        if template is None:
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        template.sqlmodel_update(
            data.model_dump(
                exclude_unset=True, exclude={"depends_on_ids", "tool_bindings"}
            )
        )
        template.updated_by = user_id
        self._db.add(template)
        if data.depends_on_ids is not None:
            dep_ids = _dedupe(data.depends_on_ids)
            await self._validate_dependencies(
                template_id, template.workflow_id, dep_ids
            )
            await self._replace_edges(template_id, dep_ids)
        if data.tool_bindings is not None:
            bindings = _dedupe_bindings(data.tool_bindings)
            await self._validate_bindings(bindings)
            await self._replace_bindings(template_id, bindings)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(template)
        return self._to_read(
            template,
            await self._deps_for(template_id),
            await self._bindings_for(template_id),
        )

    async def delete(self, template_id: str) -> None:
        """Delete the template with the given ID, raising NotFoundError if missing.

        Dependency edges referencing the template (in either direction) are
        removed by the ``ON DELETE CASCADE`` foreign keys on
        ``workflow_task_template_dependencies``.
        """
        template = await self._db.get(WorkflowTaskTemplate, template_id)
        if template is None:
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        await self._db.delete(template)
        await self._db.commit()

    # -- tool-binding helpers ------------------------------------------------

    async def _bindings_for(self, template_id: str) -> _BindingList:
        """Return the sorted tool bindings of ``template_id``."""
        stmt = select(WorkflowTaskTemplateToolBinding).where(
            WorkflowTaskTemplateToolBinding.template_id == template_id
        )
        result = await self._db.exec(stmt)
        return _sorted_bindings(
            [
                ToolBinding(mcp_server_id=row.mcp_server_id, tool_name=row.tool_name)
                for row in result.all()
            ]
        )

    async def _bindings_for_many(
        self, template_ids: Sequence[str]
    ) -> dict[str, _BindingList]:
        """Return a mapping of template ID to its sorted tool bindings for many templates."""
        out: dict[str, _BindingList] = {tid: [] for tid in template_ids}
        if not template_ids:
            return out
        stmt = select(WorkflowTaskTemplateToolBinding).where(
            col(WorkflowTaskTemplateToolBinding.template_id).in_(template_ids)
        )
        result = await self._db.exec(stmt)
        for row in result.all():
            out.setdefault(row.template_id, []).append(
                ToolBinding(mcp_server_id=row.mcp_server_id, tool_name=row.tool_name)
            )
        return {tid: _sorted_bindings(bindings) for tid, bindings in out.items()}

    async def _replace_bindings(self, template_id: str, bindings: _BindingList) -> None:
        """Delete all tool bindings of ``template_id`` and insert ``bindings`` afresh."""
        existing = await self._db.exec(
            select(WorkflowTaskTemplateToolBinding).where(
                WorkflowTaskTemplateToolBinding.template_id == template_id
            )
        )
        for row in existing.all():
            await self._db.delete(row)
        for binding in bindings:
            self._db.add(
                WorkflowTaskTemplateToolBinding(
                    template_id=template_id,
                    mcp_server_id=binding.mcp_server_id,
                    tool_name=binding.tool_name,
                )
            )

    async def _validate_bindings(self, bindings: _BindingList) -> None:
        """Reject bindings that reference an unregistered MCP server.

        Args:
            bindings: The proposed tool bindings (deduplicated).

        Raises:
            ForeignKeyViolationError: If a binding's ``mcp_server_id`` does not
                reference a registered MCP server.
        """
        for server_id in _dedupe(b.mcp_server_id for b in bindings):
            if not await self._mcp.exists(server_id):
                raise ForeignKeyViolationError("MCPServer", server_id)

    # -- dependency helpers ------------------------------------------------

    async def _deps_for(self, template_id: str) -> _StrList:
        """Return the sorted IDs of the templates that ``template_id`` depends on."""
        stmt = select(WorkflowTaskTemplateDependency.depends_on_id).where(
            WorkflowTaskTemplateDependency.template_id == template_id
        )
        result = await self._db.exec(stmt)
        return sorted(result.all())

    async def _deps_for_many(self, template_ids: Sequence[str]) -> dict[str, _StrList]:
        """Return a mapping of template ID to its sorted dependency IDs for many templates."""
        out: dict[str, _StrList] = {tid: [] for tid in template_ids}
        if not template_ids:
            return out
        stmt = select(WorkflowTaskTemplateDependency).where(
            col(WorkflowTaskTemplateDependency.template_id).in_(template_ids)
        )
        result = await self._db.exec(stmt)
        for edge in result.all():
            out.setdefault(edge.template_id, []).append(edge.depends_on_id)
        for ids in out.values():
            ids.sort()
        return out

    async def _replace_edges(self, template_id: str, dep_ids: Sequence[str]) -> None:
        """Delete all outgoing edges of ``template_id`` and insert ``dep_ids`` afresh."""
        existing = await self._db.exec(
            select(WorkflowTaskTemplateDependency).where(
                WorkflowTaskTemplateDependency.template_id == template_id
            )
        )
        for edge in existing.all():
            await self._db.delete(edge)
        for dep_id in dep_ids:
            self._db.add(
                WorkflowTaskTemplateDependency(
                    template_id=template_id, depends_on_id=dep_id
                )
            )

    async def _validate_dependencies(
        self, template_id: str, workflow_id: str, dep_ids: Sequence[str]
    ) -> None:
        """Reject self-loops, missing/cross-workflow targets, and cycles.

        Args:
            template_id: The template whose outgoing edges are being written.
            workflow_id: The workflow ``template_id`` belongs to; every target
                must belong to the same workflow.
            dep_ids: The proposed dependency target IDs (deduplicated).

        Raises:
            DependencyCycleError: If a target is the template itself or if any
                target transitively depends on ``template_id`` (which would
                close a cycle).
            ForeignKeyViolationError: If a target does not exist or belongs to a
                different workflow.
        """
        if not dep_ids:
            return
        for dep_id in dep_ids:
            if dep_id == template_id:
                raise DependencyCycleError(template_id, dep_id)
            dep = await self._db.get(WorkflowTaskTemplate, dep_id)
            if dep is None or dep.workflow_id != workflow_id:
                raise ForeignKeyViolationError("WorkflowTaskTemplate", dep_id)
        adjacency = await self._workflow_adjacency(workflow_id)
        for dep_id in dep_ids:
            if self._reaches(adjacency, dep_id, template_id):
                raise DependencyCycleError(template_id, dep_id)

    async def _workflow_adjacency(self, workflow_id: str) -> dict[str, set[str]]:
        """Build the dependency adjacency map (template ID -> its dependency IDs) for a workflow."""
        stmt = (
            select(WorkflowTaskTemplateDependency)
            .join(
                WorkflowTaskTemplate,
                col(WorkflowTaskTemplateDependency.template_id)
                == col(WorkflowTaskTemplate.id),
            )
            .where(WorkflowTaskTemplate.workflow_id == workflow_id)
        )
        result = await self._db.exec(stmt)
        adjacency: dict[str, set[str]] = {}
        for edge in result.all():
            adjacency.setdefault(edge.template_id, set()).add(edge.depends_on_id)
        return adjacency

    @staticmethod
    def _reaches(adjacency: dict[str, set[str]], start: str, target: str) -> bool:
        """Return ``True`` if ``target`` is reachable from ``start`` following dependency edges."""
        stack = list(adjacency.get(start, ()))
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency.get(node, ()))
        return False

    @staticmethod
    def _to_read(
        template: WorkflowTaskTemplate, dep_ids: _StrList, bindings: _BindingList
    ) -> WorkflowTaskTemplateRead:
        """Combine a persisted template with its resolved dependencies and tool bindings."""
        return WorkflowTaskTemplateRead.model_validate(
            {
                **template.model_dump(),
                "depends_on_ids": dep_ids,
                "tool_bindings": bindings,
            }
        )
