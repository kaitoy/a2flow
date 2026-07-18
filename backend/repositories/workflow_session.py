"""WorkflowSession repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class WorkflowSessionRepository(Protocol):
    """Interface for WorkflowSession persistence operations."""

    async def get(self, ws_id: str) -> WorkflowSession | None: ...

    async def get_by_session_id(self, session_id: str) -> WorkflowSession | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowSession]: ...

    async def create(
        self, data: WorkflowSessionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowSession: ...

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]: ...

    async def delete(self, ws_id: str) -> None: ...


class SqlWorkflowSessionRepository:
    """SQLModel-backed implementation of WorkflowSessionRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    async def _get_scoped(self, ws_id: str) -> WorkflowSession | None:
        """Return the WorkflowSession with the given ID within the current tenant, or ``None``."""
        stmt = select(WorkflowSession).where(
            WorkflowSession.id == ws_id, WorkflowSession.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, ws_id: str) -> WorkflowSession | None:
        """Return the WorkflowSession with the given ID, or ``None`` if missing."""
        return await self._get_scoped(ws_id)

    async def get_by_session_id(self, session_id: str) -> WorkflowSession | None:
        """Return the WorkflowSession for the given ADK session id, or ``None``.

        The ADK session id (the AG-UI thread id) is stored on
        :attr:`WorkflowSession.session_id`, which is distinct from the primary
        key. WorkflowTask records reference the primary key, so agent tools use
        this lookup to map the session they are running in back to its
        WorkflowSession PK.

        Args:
            session_id: The ADK session id to look up.

        Returns:
            The matching WorkflowSession, or ``None`` if no session has that id.
        """
        stmt = (
            select(WorkflowSession)
            .where(
                col(WorkflowSession.session_id) == session_id,
                WorkflowSession.tenant_id == self._tenant_id,
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
    ) -> list[WorkflowSession]:
        """Return WorkflowSessions, defaulting to ``created_at`` descending (newest first)."""
        stmt = select(WorkflowSession).where(
            WorkflowSession.tenant_id == self._tenant_id
        )
        stmt = apply_filters(stmt, WorkflowSession, filters)
        stmt = apply_sort(
            stmt,
            WorkflowSession,
            sort,
            default=[col(WorkflowSession.created_at).desc()],
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(
        self, data: WorkflowSessionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowSession:
        """Persist a new WorkflowSession with audit fields populated."""
        ws = WorkflowSession.model_validate(
            {
                **data.model_dump(),
                "workflow_id": workflow_id,
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(ws)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(ws)
        return ws

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]:
        """Return every skill revision that sessions of this skill are pinned to.

        These are the revisions a prune of the skill store must keep: each one
        is the code some WorkflowSession started against and will keep loading
        on its next agent run. Rows predating the revisioned store have a NULL
        sha and contribute nothing.

        Args:
            agent_skill_id: Identifier of the skill whose sessions to scan.

        Returns:
            The set of pinned commit shas.
        """
        stmt = select(WorkflowSession.agent_skill_commit_sha).where(
            col(WorkflowSession.agent_skill_id) == agent_skill_id,
            col(WorkflowSession.agent_skill_commit_sha).is_not(None),
            WorkflowSession.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return {sha for sha in result.all() if sha is not None}

    async def delete(self, ws_id: str) -> None:
        """Delete the WorkflowSession with the given ID, raising NotFoundError if missing."""
        ws = await self._get_scoped(ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        await self._db.delete(ws)
        await self._db.commit()
