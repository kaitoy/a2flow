"""The AG-UI events of a session's current turn, for every viewer to stream.

Holds no tenant predicate: rows carry no tenant of their own and are only ever
reached through a session the caller was first authorized for, the way a
task's dependency edges are only reached through the task.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.execution_session import SessionStreamEvent

#: Most rows one read returns; a viewer further behind catches up over reads.
_READ_LIMIT = 500


class SessionStreamRepository:
    """Appends and reads a session's streamed events."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the database session the rows are read and written through."""
        self._db = db

    async def start_run(self, session_id: str) -> None:
        """Drop the previous turn's events; its messages are in the history now."""
        await self._db.exec(
            delete(SessionStreamEvent).where(
                col(SessionStreamEvent.session_id) == session_id
            )
        )
        await self._db.commit()

    async def append(
        self, session_id: str, run_id: str, payloads: Sequence[dict[str, Any]]
    ) -> None:
        """Append events of a turn, in order, in one commit.

        Args:
            session_id: The session the turn runs in.
            run_id: The turn's AG-UI run id.
            payloads: The events, each serialized as it goes over the wire.
        """
        self._db.add_all(
            SessionStreamEvent(session_id=session_id, run_id=run_id, payload=payload)
            for payload in payloads
        )
        await self._db.commit()

    async def after(
        self, session_id: str, cursor: int
    ) -> list[tuple[int, dict[str, Any]]]:
        """Return the session's events after ``cursor``, oldest first.

        Args:
            session_id: The session to read.
            cursor: The id of the last event already seen; ``0`` for none.

        Returns:
            ``(id, payload)`` pairs, at most a few hundred per call.
        """
        stmt = (
            select(SessionStreamEvent.id, SessionStreamEvent.payload)
            .where(
                col(SessionStreamEvent.session_id) == session_id,
                col(SessionStreamEvent.id) > cursor,
            )
            .order_by(col(SessionStreamEvent.id))
            .limit(_READ_LIMIT)
        )
        return [
            (int(row[0] or 0), dict(row[1]))
            for row in (await self._db.exec(stmt)).all()
        ]

    async def cursor_before_run(self, session_id: str, run_id: str | None) -> int:
        """Return the cursor that replays ``run_id`` from its start.

        With no run under way, the cursor past every event there is: a viewer
        reading the history now has seen all of it.

        Args:
            session_id: The session to read.
            run_id: The turn under way, or ``None``.

        Returns:
            The id just before the run's first event; the session's last id
            when no run is under way; ``0`` when it has no events at all.
        """
        if run_id is None:
            stmt = select(func.max(SessionStreamEvent.id)).where(
                col(SessionStreamEvent.session_id) == session_id
            )
            return int((await self._db.exec(stmt)).one() or 0)
        stmt = select(func.min(SessionStreamEvent.id)).where(
            col(SessionStreamEvent.session_id) == session_id,
            col(SessionStreamEvent.run_id) == run_id,
        )
        first = (await self._db.exec(stmt)).one()
        if first is None:
            # The turn has written nothing yet: everything after now is its.
            return await self.cursor_before_run(session_id, None)
        return int(first) - 1
