"""WorkflowSession repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_session import WorkflowSession, WorkflowSessionCreate
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

    async def delete(self, ws_id: str) -> None: ...


class SqlWorkflowSessionRepository:
    """SQLModel-backed implementation of WorkflowSessionRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel async session used for all queries."""
        self._db = session

    async def get(self, ws_id: str) -> WorkflowSession | None:
        """Return the WorkflowSession with the given ID, or ``None`` if missing."""
        return await self._db.get(WorkflowSession, ws_id)

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
            .where(col(WorkflowSession.session_id) == session_id)
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
        stmt = apply_filters(select(WorkflowSession), WorkflowSession, filters)
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
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(ws)
        await self._db.commit()
        await self._db.refresh(ws)
        return ws

    async def delete(self, ws_id: str) -> None:
        """Delete the WorkflowSession with the given ID, raising NotFoundError if missing."""
        ws = await self._db.get(WorkflowSession, ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        await self._db.delete(ws)
        await self._db.commit()
