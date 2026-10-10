"""MCP elicitation repository: Protocol interface and SQLModel-backed implementation.

Every read is matched on the owning run as well as the id, so a question from
another run reads as missing -- the same 404-not-403 rule session files follow.
Authorization is the caller's job: the service fetches the run through the
access-tag-scoped execution repository first, so this repository carries no
visibility clause of its own.

Leaving ``pending`` is a compare-and-set. The person's answer and the waiting
call's expiry race for the same row, possibly on different replicas; whichever
write lands first is the outcome, and the other learns it lost.
"""

from datetime import datetime
from typing import Any, Protocol

from sqlmodel import col, select, update

from models.mcp_elicitation import (
    MCPElicitation,
    MCPElicitationCreate,
    MCPElicitationStatus,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories._scoped import TenantScopedRepository


class MCPElicitationRepository(Protocol):
    """Interface for MCP elicitation persistence operations."""

    async def create(
        self, data: MCPElicitationCreate, *, user_id: str
    ) -> MCPElicitation: ...

    async def get(self, elicitation_id: str) -> MCPElicitation | None: ...

    async def get_for_session(
        self, execution_id: str, session_id: str, elicitation_id: str
    ) -> MCPElicitation | None: ...

    async def answer(
        self,
        elicitation_id: str,
        *,
        status: MCPElicitationStatus,
        content: dict[str, Any] | None,
        user_id: str,
        now: datetime,
    ) -> bool: ...

    async def expire(
        self, elicitation_id: str, *, user_id: str, now: datetime
    ) -> bool: ...


class SqlMCPElicitationRepository(TenantScopedRepository[MCPElicitation]):
    """SQLModel-backed implementation of :class:`MCPElicitationRepository`."""

    model = MCPElicitation

    async def create(
        self, data: MCPElicitationCreate, *, user_id: str
    ) -> MCPElicitation:
        """Record a question a server just asked.

        Args:
            data: The question.
            user_id: Recorded as the row's creator -- the user the turn acts
                for.

        Returns:
            The stored row, ``pending``.
        """
        row = MCPElicitation.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._require_tenant(),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(row)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(row)
        return row

    async def get(self, elicitation_id: str) -> MCPElicitation | None:
        """Return a question by id, re-read from the database.

        Used by the side waiting on the answer, which polls a row another
        request may have written: ``populate_existing`` makes every poll see
        the stored state rather than the session's cached copy.

        Args:
            elicitation_id: Identifier of the question.

        Returns:
            The row, or ``None`` when it does not exist in this tenant.
        """
        stmt = self._scoped(
            select(MCPElicitation).where(col(MCPElicitation.id) == elicitation_id)
        ).execution_options(populate_existing=True)
        return (await self._db.exec(stmt)).first()

    async def get_for_session(
        self, execution_id: str, session_id: str, elicitation_id: str
    ) -> MCPElicitation | None:
        """Return a question asked in one session of one run.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            session_id: The session the question was asked in.
            elicitation_id: Identifier of the question.

        Returns:
            The row, or ``None`` when it does not belong to that session.
        """
        stmt = self._scoped(
            select(MCPElicitation).where(
                col(MCPElicitation.id) == elicitation_id,
                col(MCPElicitation.workflow_execution_id) == execution_id,
                col(MCPElicitation.session_id) == session_id,
            )
        ).execution_options(populate_existing=True)
        return (await self._db.exec(stmt)).first()

    async def answer(
        self,
        elicitation_id: str,
        *,
        status: MCPElicitationStatus,
        content: dict[str, Any] | None,
        user_id: str,
        now: datetime,
    ) -> bool:
        """Record a person's answer, if the question is still open.

        Args:
            elicitation_id: Identifier of the question.
            status: ``accepted``, ``declined`` or ``cancelled``.
            content: The submitted values, for ``accepted``.
            user_id: Who answered.
            now: The instant judged against ``expires_at``.

        Returns:
            ``True`` when this call answered it; ``False`` when it had already
            left ``pending`` or had expired.
        """
        stmt = (
            update(MCPElicitation)
            .where(
                col(MCPElicitation.id) == elicitation_id,
                col(MCPElicitation.tenant_id) == self._require_tenant(),
                col(MCPElicitation.status) == MCPElicitationStatus.pending,
                col(MCPElicitation.expires_at) > now,
            )
            .values(
                status=status,
                content=content,
                answered_by=user_id,
                answered_at=now,
                updated_by=user_id,
                updated_at=now,
            )
        )
        # No in-session sync: nothing here holds the row, and evaluating the
        # ``expires_at`` predicate in Python trips over SQLite's naive datetimes.
        result = await self._db.exec(stmt.execution_options(synchronize_session=False))
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        return bool(result.rowcount)

    async def expire(self, elicitation_id: str, *, user_id: str, now: datetime) -> bool:
        """Close a question nobody answered, if it is still open.

        Not conditioned on ``expires_at``: the waiting call also expires its
        question early when it stops waiting for another reason (the turn was
        cancelled), and nothing may answer it after that.

        Args:
            elicitation_id: Identifier of the question.
            user_id: Recorded as the row's last writer.
            now: Recorded as ``answered_at``.

        Returns:
            ``True`` when this call closed it; ``False`` when it had already
            left ``pending``.
        """
        stmt = (
            update(MCPElicitation)
            .where(
                col(MCPElicitation.id) == elicitation_id,
                col(MCPElicitation.tenant_id) == self._require_tenant(),
                col(MCPElicitation.status) == MCPElicitationStatus.pending,
            )
            .values(
                status=MCPElicitationStatus.expired,
                answered_at=now,
                updated_by=user_id,
                updated_at=now,
            )
        )
        # No in-session sync: nothing here holds the row, and evaluating the
        # ``expires_at`` predicate in Python trips over SQLite's naive datetimes.
        result = await self._db.exec(stmt.execution_options(synchronize_session=False))
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        return bool(result.rowcount)
