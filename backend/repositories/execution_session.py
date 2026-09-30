"""ExecutionSession repository: Protocol interface and SQLModel-backed implementation.

Rows are created by the server, never through the API: a run's main session
when its tasks are first assigned (:meth:`SqlExecutionSessionRepository.ensure_main`),
and branch sessions when the task graph forks.
"""

import builtins
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from models.execution_session import ExecutionSession
from repositories._scoped import TenantScopedRepository


class ExecutionSessionRepository(Protocol):
    """Interface for ExecutionSession persistence operations."""

    async def list_for_execution(
        self, execution_id: str
    ) -> builtins.list[ExecutionSession]: ...

    async def ensure_main(
        self, *, execution_id: str, session_id: str, user_id: str
    ) -> ExecutionSession: ...


class SqlExecutionSessionRepository(TenantScopedRepository[ExecutionSession]):
    """SQLModel-backed implementation of ExecutionSessionRepository."""

    model = ExecutionSession

    async def list_for_execution(
        self, execution_id: str
    ) -> builtins.list[ExecutionSession]:
        """Return every session of a run, oldest first.

        Args:
            execution_id: Primary key of the workflow execution.

        Returns:
            The run's sessions ordered by ``created_at``, the main session first.
        """
        stmt = self._scoped(
            select(ExecutionSession).where(
                col(ExecutionSession.workflow_execution_id) == execution_id
            )
        ).order_by(col(ExecutionSession.created_at), col(ExecutionSession.id))
        return list((await self._db.exec(stmt)).all())

    async def ensure_main(
        self, *, execution_id: str, session_id: str, user_id: str
    ) -> ExecutionSession:
        """Return the run's main-session row, creating it if it does not exist yet.

        Idempotent under concurrency: when two writers race to create it, the
        loser's insert fails on the primary key and it reads the winner's row.

        Args:
            execution_id: Primary key of the workflow execution.
            session_id: The execution's ``session_id``, which the row shares.
            user_id: Recorded on the audit fields of a newly created row.

        Returns:
            The main-session row.
        """
        existing = await self._get_scoped(session_id)
        if existing is not None:
            return existing
        row = ExecutionSession(
            id=session_id,
            workflow_execution_id=execution_id,
            tenant_id=self._require_tenant(),
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(row)
        try:
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            raced = await self._get_scoped(session_id)
            if raced is None:
                raise
            return raced
        await self._db.refresh(row)
        return row
