"""WorkflowTask repository: Protocol interface and SQLModel-backed implementation.

Tasks form a directed acyclic graph (DAG): each task may depend on zero or more
other tasks in the same session. Dependency edges are persisted in the
``workflow_task_dependencies`` join table and exposed on
:class:`WorkflowTaskRead` as ``depends_on_ids``. The repository enforces three
invariants whenever edges are written: every dependency target must exist and
belong to the same session, a task may not depend on itself, and the resulting
edge set must remain acyclic.

Tasks may additionally bind MCP tools (a registered server plus a tool name).
Bindings are persisted in the ``workflow_task_tool_bindings`` join table and
exposed on :class:`WorkflowTaskRead` as ``tool_bindings``; every bound server
must exist when bindings are written.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_task import (
    ToolBinding,
    WorkflowTask,
    WorkflowTaskCreate,
    WorkflowTaskDependency,
    WorkflowTaskRead,
    WorkflowTaskToolBinding,
    WorkflowTaskUpdate,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import (
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
)
from repositories.mcp_server import MCPServerRepository
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.workflow_session import WorkflowSessionRepository

# Module-level aliases for ``list[...]`` types. The repository defines a method
# named ``list``, which causes mypy to resolve a bare ``list[...]`` annotation in
# methods declared after it to that method rather than the builtin; the aliases
# are evaluated in module scope where ``list`` is unambiguously the builtin.
_StrList = list[str]
_BindingList = list[ToolBinding]


class WorkflowTaskRepository(Protocol):
    """Interface for WorkflowTask persistence operations."""

    async def get(self, task_id: str) -> WorkflowTaskRead | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_session_id: str | None = None,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowTaskRead]: ...

    async def create(
        self, data: WorkflowTaskCreate, *, user_id: str
    ) -> WorkflowTaskRead: ...

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, user_id: str
    ) -> WorkflowTaskRead: ...

    async def delete(self, task_id: str) -> None: ...


class SqlWorkflowTaskRepository:
    """SQLModel-backed implementation of WorkflowTaskRepository.

    Validates that the referenced ``workflow_session_id`` exists before creating
    a task, raising ForeignKeyViolationError if it does not. Dependency edges are
    validated for existence, same-session membership, self-loops, and acyclicity
    before being written; reads resolve a task's outgoing edges into
    ``depends_on_ids``. Tool bindings are validated against the registered MCP
    servers before being written; reads resolve them into ``tool_bindings``.
    """

    def __init__(
        self,
        session: AsyncSession,
        ws_repo: WorkflowSessionRepository,
        mcp_repo: MCPServerRepository,
    ) -> None:
        """Store the session and the WorkflowSession/MCPServer repos for FK checks."""
        self._db = session
        self._ws = ws_repo
        self._mcp = mcp_repo

    async def get(self, task_id: str) -> WorkflowTaskRead | None:
        """Return the WorkflowTask with the given ID resolved into a read model, or ``None``."""
        task = await self._db.get(WorkflowTask, task_id)
        if task is None:
            return None
        return self._to_read(
            task, await self._deps_for(task_id), await self._bindings_for(task_id)
        )

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_session_id: str | None = None,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowTaskRead]:
        """Return WorkflowTasks, defaulting to ``position`` then ``created_at`` order.

        When ``workflow_session_id`` is supplied, only tasks belonging to that
        session are returned. Each task's outgoing dependency edges are resolved
        into ``depends_on_ids`` with a single batched query.
        """
        stmt = select(WorkflowTask)
        if workflow_session_id is not None:
            stmt = stmt.where(WorkflowTask.workflow_session_id == workflow_session_id)
        stmt = apply_filters(stmt, WorkflowTask, filters)
        stmt = apply_sort(
            stmt,
            WorkflowTask,
            sort,
            default=[
                col(WorkflowTask.position).asc(),
                col(WorkflowTask.created_at).asc(),
            ],
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        tasks = list(result.all())
        deps = await self._deps_for_many([t.id for t in tasks])
        bindings = await self._bindings_for_many([t.id for t in tasks])
        return [
            self._to_read(t, deps.get(t.id, []), bindings.get(t.id, [])) for t in tasks
        ]

    async def create(
        self, data: WorkflowTaskCreate, *, user_id: str
    ) -> WorkflowTaskRead:
        """Create a new WorkflowTask after validating the parent session, dependencies, and tool bindings."""
        if await self._ws.get(data.workflow_session_id) is None:
            raise ForeignKeyViolationError("WorkflowSession", data.workflow_session_id)
        task = WorkflowTask.model_validate(
            {
                **data.model_dump(exclude={"depends_on_ids", "tool_bindings"}),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        dep_ids = _dedupe(data.depends_on_ids or [])
        await self._validate_dependencies(task.id, data.workflow_session_id, dep_ids)
        bindings = _dedupe_bindings(data.tool_bindings or [])
        await self._validate_bindings(bindings)
        self._db.add(task)
        for dep_id in dep_ids:
            self._db.add(WorkflowTaskDependency(task_id=task.id, depends_on_id=dep_id))
        for binding in bindings:
            self._db.add(
                WorkflowTaskToolBinding(
                    task_id=task.id,
                    mcp_server_id=binding.mcp_server_id,
                    tool_name=binding.tool_name,
                )
            )
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(task)
        return self._to_read(task, sorted(dep_ids), _sorted_bindings(bindings))

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, user_id: str
    ) -> WorkflowTaskRead:
        """Apply a partial update to an existing WorkflowTask.

        When ``data.depends_on_ids`` is ``None`` the task's edges are left
        unchanged; when it is a list the full set of outgoing edges is replaced
        after validation. ``data.tool_bindings`` follows the same semantics for
        the task's bound MCP tools. ``workflow_session_id`` is not part of
        ``WorkflowTaskUpdate`` so no parent re-validation is needed here.
        """
        task = await self._db.get(WorkflowTask, task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        task.sqlmodel_update(
            data.model_dump(
                exclude_unset=True, exclude={"depends_on_ids", "tool_bindings"}
            )
        )
        task.updated_by = user_id
        self._db.add(task)
        if data.depends_on_ids is not None:
            dep_ids = _dedupe(data.depends_on_ids)
            await self._validate_dependencies(
                task_id, task.workflow_session_id, dep_ids
            )
            await self._replace_edges(task_id, dep_ids)
        if data.tool_bindings is not None:
            bindings = _dedupe_bindings(data.tool_bindings)
            await self._validate_bindings(bindings)
            await self._replace_bindings(task_id, bindings)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(task)
        return self._to_read(
            task, await self._deps_for(task_id), await self._bindings_for(task_id)
        )

    async def delete(self, task_id: str) -> None:
        """Delete the WorkflowTask with the given ID, raising NotFoundError if missing.

        Dependency edges referencing the task (in either direction) are removed
        by the ``ON DELETE CASCADE`` foreign keys on ``workflow_task_dependencies``.
        """
        task = await self._db.get(WorkflowTask, task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        await self._db.delete(task)
        await self._db.commit()

    # -- tool-binding helpers ------------------------------------------------

    async def _bindings_for(self, task_id: str) -> _BindingList:
        """Return the sorted tool bindings of ``task_id``."""
        stmt = select(WorkflowTaskToolBinding).where(
            WorkflowTaskToolBinding.task_id == task_id
        )
        result = await self._db.exec(stmt)
        return _sorted_bindings(
            [
                ToolBinding(mcp_server_id=row.mcp_server_id, tool_name=row.tool_name)
                for row in result.all()
            ]
        )

    async def _bindings_for_many(
        self, task_ids: Sequence[str]
    ) -> dict[str, _BindingList]:
        """Return a mapping of task ID to its sorted tool bindings for many tasks."""
        out: dict[str, _BindingList] = {tid: [] for tid in task_ids}
        if not task_ids:
            return out
        stmt = select(WorkflowTaskToolBinding).where(
            col(WorkflowTaskToolBinding.task_id).in_(task_ids)
        )
        result = await self._db.exec(stmt)
        for row in result.all():
            out.setdefault(row.task_id, []).append(
                ToolBinding(mcp_server_id=row.mcp_server_id, tool_name=row.tool_name)
            )
        return {tid: _sorted_bindings(bindings) for tid, bindings in out.items()}

    async def _replace_bindings(self, task_id: str, bindings: _BindingList) -> None:
        """Delete all tool bindings of ``task_id`` and insert ``bindings`` afresh."""
        existing = await self._db.exec(
            select(WorkflowTaskToolBinding).where(
                WorkflowTaskToolBinding.task_id == task_id
            )
        )
        for row in existing.all():
            await self._db.delete(row)
        for binding in bindings:
            self._db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id,
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

    async def _deps_for(self, task_id: str) -> _StrList:
        """Return the sorted IDs of the tasks that ``task_id`` depends on."""
        stmt = select(WorkflowTaskDependency.depends_on_id).where(
            WorkflowTaskDependency.task_id == task_id
        )
        result = await self._db.exec(stmt)
        return sorted(result.all())

    async def _deps_for_many(self, task_ids: Sequence[str]) -> dict[str, _StrList]:
        """Return a mapping of task ID to its sorted dependency IDs for many tasks."""
        out: dict[str, _StrList] = {tid: [] for tid in task_ids}
        if not task_ids:
            return out
        stmt = select(WorkflowTaskDependency).where(
            col(WorkflowTaskDependency.task_id).in_(task_ids)
        )
        result = await self._db.exec(stmt)
        for edge in result.all():
            out.setdefault(edge.task_id, []).append(edge.depends_on_id)
        for ids in out.values():
            ids.sort()
        return out

    async def _replace_edges(self, task_id: str, dep_ids: Sequence[str]) -> None:
        """Delete all outgoing edges of ``task_id`` and insert ``dep_ids`` afresh."""
        existing = await self._db.exec(
            select(WorkflowTaskDependency).where(
                WorkflowTaskDependency.task_id == task_id
            )
        )
        for edge in existing.all():
            await self._db.delete(edge)
        for dep_id in dep_ids:
            self._db.add(WorkflowTaskDependency(task_id=task_id, depends_on_id=dep_id))

    async def _validate_dependencies(
        self, task_id: str, session_id: str, dep_ids: Sequence[str]
    ) -> None:
        """Reject self-loops, missing/cross-session targets, and cycles.

        Args:
            task_id: The task whose outgoing edges are being written.
            session_id: The session ``task_id`` belongs to; every target must
                belong to the same session.
            dep_ids: The proposed dependency target IDs (deduplicated).

        Raises:
            DependencyCycleError: If a target is the task itself or if any target
                transitively depends on ``task_id`` (which would close a cycle).
            ForeignKeyViolationError: If a target does not exist or belongs to a
                different session.
        """
        if not dep_ids:
            return
        for dep_id in dep_ids:
            if dep_id == task_id:
                raise DependencyCycleError(task_id, dep_id)
            dep = await self._db.get(WorkflowTask, dep_id)
            if dep is None or dep.workflow_session_id != session_id:
                raise ForeignKeyViolationError("WorkflowTask", dep_id)
        adjacency = await self._session_adjacency(session_id)
        for dep_id in dep_ids:
            if self._reaches(adjacency, dep_id, task_id):
                raise DependencyCycleError(task_id, dep_id)

    async def _session_adjacency(self, session_id: str) -> dict[str, set[str]]:
        """Build the dependency adjacency map (task ID -> its dependency IDs) for a session."""
        stmt = (
            select(WorkflowTaskDependency)
            .join(
                WorkflowTask,
                col(WorkflowTaskDependency.task_id) == col(WorkflowTask.id),
            )
            .where(WorkflowTask.workflow_session_id == session_id)
        )
        result = await self._db.exec(stmt)
        adjacency: dict[str, set[str]] = {}
        for edge in result.all():
            adjacency.setdefault(edge.task_id, set()).add(edge.depends_on_id)
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
        task: WorkflowTask, dep_ids: _StrList, bindings: _BindingList
    ) -> WorkflowTaskRead:
        """Combine a persisted task with its resolved dependencies and tool bindings."""
        return WorkflowTaskRead.model_validate(
            {
                **task.model_dump(),
                "depends_on_ids": dep_ids,
                "tool_bindings": bindings,
            }
        )


def _dedupe(ids: Iterable[str]) -> list[str]:
    """Return the IDs with duplicates removed, preserving first-seen order."""
    return list(dict.fromkeys(ids))


def _dedupe_bindings(bindings: Iterable[ToolBinding]) -> list[ToolBinding]:
    """Return the bindings with duplicate (server, tool) pairs removed, order preserved."""
    seen: dict[tuple[str, str], ToolBinding] = {}
    for binding in bindings:
        seen.setdefault((binding.mcp_server_id, binding.tool_name), binding)
    return list(seen.values())


def _sorted_bindings(bindings: Iterable[ToolBinding]) -> list[ToolBinding]:
    """Return the bindings sorted by (server ID, tool name) for deterministic reads."""
    return sorted(bindings, key=lambda b: (b.mcp_server_id, b.tool_name))
