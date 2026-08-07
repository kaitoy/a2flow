"""WorkflowExecution repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_execution import WorkflowExecution, WorkflowExecutionCreate
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class WorkflowExecutionRepository(Protocol):
    """Interface for WorkflowExecution persistence operations."""

    async def get(self, execution_id: str) -> WorkflowExecution | None: ...

    async def get_by_session_id(self, session_id: str) -> WorkflowExecution | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowExecution]: ...

    async def create(
        self, data: WorkflowExecutionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowExecution: ...

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]: ...

    async def delete(self, execution_id: str) -> None: ...


class SqlWorkflowExecutionRepository:
    """SQLModel-backed implementation of WorkflowExecutionRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    async def _get_scoped(self, execution_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution with the given ID within the current tenant, or ``None``."""
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, execution_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution with the given ID, or ``None`` if missing."""
        return await self._get_scoped(execution_id)

    async def get_by_session_id(self, session_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution for the given ADK session id, or ``None``.

        The ADK session id (the AG-UI thread id) is stored on
        :attr:`WorkflowExecution.session_id`, which is distinct from the primary
        key. WorkflowTask records reference the primary key, so agent tools use
        this lookup to map the workflow session they run in back to its
        WorkflowExecution PK.

        Args:
            session_id: The ADK session id to look up.

        Returns:
            The matching WorkflowExecution, or ``None`` if no execution has that
            session id.
        """
        stmt = (
            select(WorkflowExecution)
            .where(
                col(WorkflowExecution.session_id) == session_id,
                WorkflowExecution.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowExecution]:
        """Return WorkflowExecutions, defaulting to ``created_at`` descending (newest first)."""
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.tenant_id == self._tenant_id
        )
        stmt = apply_filters(
            stmt, WorkflowExecution, filters, readable=WorkflowExecution
        )
        stmt = apply_sort(
            stmt,
            WorkflowExecution,
            sort,
            default=[col(WorkflowExecution.created_at).desc()],
            readable=WorkflowExecution,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(
        self, data: WorkflowExecutionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowExecution:
        """Persist a new WorkflowExecution with audit fields populated."""
        execution = WorkflowExecution.model_validate(
            {
                **data.model_dump(),
                "workflow_id": workflow_id,
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(execution)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(execution)
        return execution

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]:
        """Return every skill revision that executions of this skill are pinned to.

        These are the revisions a prune of the skill store must keep: each one
        is the code some WorkflowExecution started against and will keep loading
        on its next agent run. Rows predating the revisioned store have a NULL
        sha and contribute nothing.

        Args:
            agent_skill_id: Identifier of the skill whose executions to scan.

        Returns:
            The set of pinned commit shas.
        """
        stmt = select(WorkflowExecution.agent_skill_commit_sha).where(
            col(WorkflowExecution.agent_skill_id) == agent_skill_id,
            col(WorkflowExecution.agent_skill_commit_sha).is_not(None),
            WorkflowExecution.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return {sha for sha in result.all() if sha is not None}

    async def delete(self, execution_id: str) -> None:
        """Delete the WorkflowExecution with the given ID, raising NotFoundError if missing."""
        execution = await self._get_scoped(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._db.delete(execution)
        await self._db.commit()
