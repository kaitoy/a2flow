"""ExecutionSession repository: Protocol interface and SQLModel-backed implementation.

Rows are created by the server, never through the API: a run's main session
when its tasks are first assigned (:meth:`SqlExecutionSessionRepository.ensure_main`),
and branch sessions when the task graph forks.
"""

import builtins
import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Enum, and_, case, literal
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select, update

from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.workflow_execution import WorkflowExecution, WorkflowExecutionStatus
from repositories._scoped import TenantScopedRepository


class ExecutionSessionRepository(Protocol):
    """Interface for ExecutionSession persistence operations."""

    async def list_for_execution(
        self, execution_id: str
    ) -> builtins.list[ExecutionSession]: ...

    async def ensure_main(
        self, *, execution_id: str, session_id: str, user_id: str
    ) -> ExecutionSession: ...

    async def get(self, session_id: str) -> ExecutionSession | None: ...

    async def queue_input(
        self, session_id: str, pending_input: dict[str, Any], *, user_id: str
    ) -> bool: ...

    async def set_state(
        self,
        session_id: str,
        *,
        status: ExecutionSessionStatus,
        user_id: str,
        waiting_on: builtins.list[dict[str, Any]] | None = None,
        clear_input: bool = False,
        summary: str | None = None,
    ) -> None: ...

    async def mark_run(
        self,
        session_id: str,
        *,
        run_id: str | None,
        event_index: int,
        user_id: str,
        clear_input: bool = False,
    ) -> None: ...

    async def create_branch(
        self, *, execution_id: str, parent_id: str, user_id: str
    ) -> ExecutionSession: ...

    async def delete(self, session_id: str) -> None: ...

    async def mark_forked(
        self, session_id: str, *, event_count: int, user_id: str
    ) -> None: ...

    async def set_resume_at(
        self, session_id: str, at: datetime, *, user_id: str
    ) -> None: ...


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

    async def get(self, session_id: str) -> ExecutionSession | None:
        """Return the session with the given ADK id, or ``None``."""
        return await self._get_scoped(session_id)

    async def queue_input(
        self, session_id: str, pending_input: dict[str, Any], *, user_id: str
    ) -> bool:
        """Hand a session its next input and mark it ``queued``, unless it is busy.

        A compare-and-set: a session already ``queued`` or ``running`` keeps
        the input it has, so two writers queueing at once cannot overwrite
        each other and a turn in flight never has its input swapped under it.

        Args:
            session_id: The session to queue.
            pending_input: The input, as a ``SessionInput`` dump.
            user_id: Recorded on the row's ``updated_by`` when the input lands.

        Returns:
            ``True`` when the input was queued, ``False`` when the session was
            busy or not found.

        Queued input also recomputes the run's status (see
        :meth:`_sync_execution_status`), in the same commit.
        """
        busy = (ExecutionSessionStatus.queued, ExecutionSessionStatus.running)
        stmt = (
            update(ExecutionSession)
            .where(
                col(ExecutionSession.id) == session_id,
                col(ExecutionSession.tenant_id) == self._require_tenant(),
                col(ExecutionSession.status).not_in(busy),
            )
            .values(
                status=ExecutionSessionStatus.queued,
                pending_input=pending_input,
                # Input wakes a ``scheduled`` session early: it no longer waits.
                resume_at=None,
                updated_by=user_id,
            )
        )
        result = await self._db.exec(stmt)
        if result.rowcount:
            await self._sync_execution_status(session_id)
        await self._db.commit()
        return bool(result.rowcount)

    async def set_state(
        self,
        session_id: str,
        *,
        status: ExecutionSessionStatus,
        user_id: str,
        waiting_on: builtins.list[dict[str, Any]] | None = None,
        clear_input: bool = False,
        summary: str | None = None,
    ) -> None:
        """Record where a session stands after (or at the start of) a turn.

        Args:
            session_id: The session to update.
            status: Its new status.
            user_id: Recorded on the row's ``updated_by``.
            waiting_on: The calls it is now paused on; left unchanged when
                ``None``.
            clear_input: Whether the turn consumed its queued input.
            summary: What a finishing branch reported; left unchanged when
                ``None``.

        Any status but ``scheduled`` also clears ``resume_at``: only a
        ``scheduled`` session waits on a time. The run's status is recomputed
        in the same commit (see :meth:`_sync_execution_status`).
        """
        values: dict[str, Any] = {"status": status, "updated_by": user_id}
        if status is not ExecutionSessionStatus.scheduled:
            values["resume_at"] = None
        if summary is not None:
            values["summary"] = summary
        await self._update(
            session_id, values, waiting_on, clear_input, sync_execution=True
        )

    async def create_branch(
        self, *, execution_id: str, parent_id: str, user_id: str
    ) -> ExecutionSession:
        """Create a branch session forked from ``parent_id``, not yet due to run.

        Its ADK session is copied from the parent on its first turn, not here
        (:func:`infrastructure.session_fork.fork_adk_session`), so it starts
        from the parent's context as it stands when the branch actually runs.

        Args:
            execution_id: Primary key of the workflow execution.
            parent_id: The session it is forked from.
            user_id: Recorded on the audit fields.

        Returns:
            The new ``idle`` row; queueing its first input is what makes it due.
        """
        row = ExecutionSession(
            id=str(uuid.uuid4()),
            workflow_execution_id=execution_id,
            parent_id=parent_id,
            tenant_id=self._require_tenant(),
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def delete(self, session_id: str) -> None:
        """Delete a session row; a no-op when it does not exist in the tenant."""
        row = await self._get_scoped(session_id)
        if row is not None:
            await self._db.delete(row)
            await self._db.commit()

    async def mark_forked(
        self, session_id: str, *, event_count: int, user_id: str
    ) -> None:
        """Record how many leading ADK events a branch copied from its parent."""
        await self._update(
            session_id,
            {"fork_event_count": event_count, "updated_by": user_id},
            None,
            False,
        )

    async def set_resume_at(
        self, session_id: str, at: datetime, *, user_id: str
    ) -> None:
        """Record when a session is to run again; settling its turn schedules it.

        Args:
            session_id: The session whose agent called ``wait_until``.
            at: When it is due again, timezone-aware.
            user_id: Recorded on the row's ``updated_by``.
        """
        await self._update(
            session_id, {"resume_at": at, "updated_by": user_id}, None, False
        )

    async def mark_run(
        self,
        session_id: str,
        *,
        run_id: str | None,
        event_index: int,
        user_id: str,
        clear_input: bool = False,
    ) -> None:
        """Record which turn is under way and where its events start in the history.

        Args:
            session_id: The session running the turn.
            run_id: The turn's AG-UI run id, or ``None`` once it has ended.
            event_index: How many ADK events the session held when it started.
            user_id: Recorded on the row's ``updated_by``.
            clear_input: Whether to drop the queued input too -- once a turn
                has ended its input is in the history.
        """
        await self._update(
            session_id,
            {
                "active_run_id": run_id,
                "run_event_index": event_index,
                "updated_by": user_id,
            },
            None,
            clear_input,
        )

    async def _update(
        self,
        session_id: str,
        values: dict[str, Any],
        waiting_on: builtins.list[dict[str, Any]] | None,
        clear_input: bool,
        *,
        sync_execution: bool = False,
    ) -> None:
        """Write ``values`` (plus the optional waiting list and input reset) to one row.

        With ``sync_execution``, the run's status is recomputed before the commit.
        """
        if waiting_on is not None:
            values["waiting_on"] = waiting_on
        if clear_input:
            values["pending_input"] = None
        await self._db.exec(
            update(ExecutionSession)
            .where(
                col(ExecutionSession.id) == session_id,
                col(ExecutionSession.tenant_id) == self._require_tenant(),
            )
            .values(**values)
        )
        if sync_execution:
            await self._sync_execution_status(session_id)
        await self._db.commit()

    async def _sync_execution_status(self, session_id: str) -> None:
        """Set the session's run to ``scheduled`` or ``running`` from its sessions.

        The run is ``scheduled`` when at least one of its sessions is
        ``scheduled`` and every other one is ``idle`` or ``done`` -- nothing
        is happening but a wait on a time -- and ``running`` otherwise. A
        finished run (``finished_at`` set) is never touched. Runs as one
        ``UPDATE`` and leaves the commit to the caller.

        Args:
            session_id: Any session of the run to recompute.
        """
        siblings = select(ExecutionSession.id).where(
            col(ExecutionSession.workflow_execution_id) == WorkflowExecution.id
        )
        quiet = (
            ExecutionSessionStatus.scheduled,
            ExecutionSessionStatus.idle,
            ExecutionSessionStatus.done,
        )
        waiting = and_(
            siblings.where(
                col(ExecutionSession.status) == ExecutionSessionStatus.scheduled
            ).exists(),
            ~siblings.where(col(ExecutionSession.status).not_in(quiet)).exists(),
        )
        owner = (
            select(ExecutionSession.workflow_execution_id)
            .where(col(ExecutionSession.id) == session_id)
            .scalar_subquery()
        )
        # Typed so PostgreSQL casts the CASE to its native enum, not VARCHAR.
        status_type = Enum(WorkflowExecutionStatus)
        await self._db.exec(
            update(WorkflowExecution)
            .where(
                col(WorkflowExecution.id) == owner,
                col(WorkflowExecution.tenant_id) == self._require_tenant(),
                col(WorkflowExecution.finished_at).is_(None),
            )
            .values(
                status=case(
                    (waiting, literal(WorkflowExecutionStatus.scheduled, status_type)),
                    else_=literal(WorkflowExecutionStatus.running, status_type),
                )
            )
        )
