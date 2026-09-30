"""Deliberately tenant-unscoped: the sessions the server has turns to run for.

The session runner (:mod:`services.session_runner`) is one per process and
serves every tenant: it runs the turns nobody's browser is driving -- a run's
kickoff, its resumption after an approval is decided. It starts from nothing
but "which sessions have work?", so the question has to be asked across
tenants; each row it gets back carries its ``tenant_id``, and everything the
runner does *for* that session is built scoped to that tenant.

This is the one query here and it returns ids only, never a session's content.
"""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.execution_session import ExecutionSession, ExecutionSessionStatus

#: How many due sessions one poll considers. The runner's concurrency is far
#: below this; the rest are picked up on the next poll.
_DUE_LIMIT = 100


async def due_sessions(db: AsyncSession) -> list[tuple[str, str]]:
    """Return ``(session_id, tenant_id)`` of every session with a turn to run.

    That is a ``queued`` session, and a ``running`` one: a turn in progress
    holds the session's run lock, so the runner skips it, while a ``running``
    row whose lock is free belongs to a process that died mid-turn and is
    resumed.

    Args:
        db: The database session to query.

    Returns:
        The due sessions, oldest change first.
    """
    stmt = (
        select(ExecutionSession.id, ExecutionSession.tenant_id)
        .where(
            col(ExecutionSession.status).in_(
                (ExecutionSessionStatus.queued, ExecutionSessionStatus.running)
            )
        )
        .order_by(col(ExecutionSession.updated_at))
        .limit(_DUE_LIMIT)
    )
    return [(row[0], row[1]) for row in (await db.exec(stmt)).all()]
