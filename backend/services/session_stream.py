"""Relaying a session's turn to everyone watching it, on any replica.

The process running a turn writes its AG-UI events to
:class:`models.execution_session.SessionStreamEvent` as they come
(:class:`StreamWriter`); every viewer's SSE connection reads them back from
there (:func:`stream_events`), whichever replica it reached. A viewer joins at
a cursor -- the last event it already has -- and its stream ends with the turn,
after which it re-reads the history and subscribes again.
"""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ag_ui.core import BaseEvent, EventType
from sqlmodel.ext.asyncio.session import AsyncSession

from repositories.session_stream import SessionStreamRepository

#: Events that only extend the one before them. They are batched rather than
#: committed one by one, which would cost a write per token.
_DELTA_EVENTS = frozenset(
    {
        EventType.TEXT_MESSAGE_CONTENT,
        EventType.TOOL_CALL_ARGS,
        EventType.REASONING_MESSAGE_CONTENT,
    }
)

#: The longest a delta waits in the writer's buffer before being written.
_FLUSH_SECONDS = 0.1

#: How long a viewer with nothing to read waits before looking again. Events
#: written by this process wake it at once; this bounds the delay for events
#: written by another replica. ponytail: polling; a ``LISTEN``/``NOTIFY``
#: channel would remove the delay if viewers ever make the reads costly.
_POLL_SECONDS = 1.0

#: How often an idle stream sends a comment, so proxies keep it open.
_KEEPALIVE_SECONDS = 15.0

#: Events that end a turn, and so a viewer's stream.
_TERMINAL = frozenset({EventType.RUN_FINISHED.value, EventType.RUN_ERROR.value})

_written = asyncio.Event()


def _notify() -> None:
    """Wake this process's viewers: there are new events to read."""
    _written.set()
    _written.clear()


def serialize(event: BaseEvent) -> dict[str, Any]:
    """Serialize an event the way it goes over the wire to a browser."""
    payload: dict[str, Any] = event.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return payload


class StreamWriter:
    """Writes one turn's events for its viewers, batching token deltas."""

    def __init__(self, db: AsyncSession, session_id: str, run_id: str) -> None:
        """Bind the writer to a turn.

        Args:
            db: The database session the turn runs on.
            session_id: The session the turn runs in.
            run_id: The turn's AG-UI run id.
        """
        self._repo = SessionStreamRepository(db)
        self._session_id = session_id
        self._run_id = run_id
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()

    async def start(self) -> None:
        """Drop the previous turn's events before this one writes its first."""
        await self._repo.start_run(self._session_id)

    async def write(self, event: BaseEvent) -> None:
        """Queue an event, writing the buffer out unless it is a fresh delta."""
        if event.type == EventType.MESSAGES_SNAPSHOT:
            # The whole conversation, sent at the end of every turn: a viewer
            # re-reads the history then anyway, and for a forked session it
            # would replay the parent's conversation too.
            return
        self._buffer.append(serialize(event))
        stale = time.monotonic() - self._last_flush >= _FLUSH_SECONDS
        if event.type not in _DELTA_EVENTS or stale:
            await self.flush()

    async def flush(self) -> None:
        """Write out whatever is buffered."""
        if self._buffer:
            await self._repo.append(self._session_id, self._run_id, self._buffer)
            self._buffer = []
            _notify()
        self._last_flush = time.monotonic()


async def stream_events(
    session_id: str,
    cursor: int,
    *,
    open_db: Callable[[], AsyncSession],
    disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """Yield a session's events after ``cursor`` as SSE, until a turn ends.

    Waits for the next turn when none is under way, sending keepalive comments
    meanwhile, and stops after the turn's last event or when the viewer leaves.

    Args:
        session_id: The session to stream.
        cursor: The id of the last event the viewer already has.
        open_db: Opens a database session for each read.
        disconnected: Tells whether the viewer has gone.

    Yields:
        SSE frames, each carrying one event and its id.
    """
    last_sent = time.monotonic()
    while True:
        async with open_db() as db:
            rows = await SessionStreamRepository(db).after(session_id, cursor)
        for event_id, payload in rows:
            cursor = event_id
            last_sent = time.monotonic()
            yield f"id: {event_id}\ndata: {json.dumps(payload)}\n\n"
            if payload.get("type") in _TERMINAL:
                return
        if rows:
            continue
        if await disconnected():
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_written.wait(), _POLL_SECONDS)
        if time.monotonic() - last_sent >= _KEEPALIVE_SECONDS:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
