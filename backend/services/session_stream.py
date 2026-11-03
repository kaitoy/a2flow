"""Relaying a session's turn to everyone watching it, on any replica.

The process running a turn writes its AG-UI events to
:class:`models.execution_session.SessionStreamEvent` as they come
(:class:`StreamWriter`); every viewer's SSE connection reads them back from
there (:func:`stream_events`), whichever replica it reached. A viewer joins at
a cursor -- the last event it already has -- and its stream ends with the turn,
after which it re-reads the history and subscribes again.

A viewer reads only when woken for its own session. On SQLite -- one process
by construction -- the writer wakes its viewers directly
(:func:`notify_viewers`). On PostgreSQL every append also issues a ``NOTIFY``
in its own transaction (:meth:`SessionStreamRepository.append`), and each
process holds one ``LISTEN`` connection (:func:`run_stream_listener`) that
wakes that session's viewers on whichever replica they are; a slow poll only
backs it up.
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ag_ui.core import BaseEvent, EventType
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.database import DB_URL, is_sqlite_url
from infrastructure.locks import dedicated_engine
from repositories.session_stream import STREAM_CHANNEL, SessionStreamRepository

logger = logging.getLogger(__name__)

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

#: How often an idle stream sends a comment, so proxies keep it open.
_KEEPALIVE_SECONDS = 15.0

#: How long a viewer with nothing to read waits before looking again, even
#: unwoken. ponytail: a backstop for a ``LISTEN`` connection that died without
#: closing (half-open TCP goes unnoticed), which delays its replica's viewers by
#: up to this long; a heartbeat on that connection would detect it sooner.
_POLL_SECONDS = _KEEPALIVE_SECONDS

#: How long the listener waits before reconnecting after losing its connection.
_RELISTEN_SECONDS = 5.0

#: Events that end a turn, and so a viewer's stream.
_TERMINAL = frozenset({EventType.RUN_FINISHED.value, EventType.RUN_ERROR.value})

#: Each session's viewers in this process, one event apiece, set to wake it.
_viewers: dict[str, set[asyncio.Event]] = {}

#: Whether :func:`run_stream_listener` is listening, so that ``NOTIFY`` --
#: rather than the writer -- wakes this process's viewers.
_listening = False

#: Headers every SSE response carries. ``no-transform`` keeps an intermediary
#: from compressing the stream: the Next.js server in front of the API gzips
#: what it proxies unless told not to, and a gzip stream reaches the browser
#: only when it closes -- so a turn waiting on a person (an MCP elicitation)
#: would never show the question it is waiting on. ``X-Accel-Buffering`` asks
#: nginx not to buffer it either.
SSE_HEADERS = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache, no-transform"}


def _wake(session_id: str) -> None:
    """Wake this process's viewers of one session."""
    for woken in _viewers.get(session_id, ()):
        woken.set()


def _wake_all() -> None:
    """Wake every viewer in this process, of whatever session."""
    for viewers in _viewers.values():
        for woken in viewers:
            woken.set()


def notify_viewers(session_id: str) -> None:
    """Wake this process's viewers of a session: it has new events to read.

    Called by whatever appends to a session's stream -- the turn's own writer,
    or a question an MCP server asked mid-turn (see
    :mod:`infrastructure.mcp_elicitation`) -- after the append commits. While
    the listener is up this does nothing: the append's own ``NOTIFY`` comes
    back to this process too, and waking the viewers twice would cost each
    of them a read that finds nothing.

    Args:
        session_id: The session appended to.
    """
    if not _listening:
        _wake(session_id)


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
        """Write out whatever is buffered, then wake the session's viewers."""
        if self._buffer:
            await self._repo.append(self._session_id, self._run_id, self._buffer)
            self._buffer = []
            notify_viewers(self._session_id)
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
    Reads only when woken for this session (or every :data:`_POLL_SECONDS`).
    The wake is cleared before each read rather than after it, so one that
    arrives mid-read is not lost.

    Args:
        session_id: The session to stream.
        cursor: The id of the last event the viewer already has.
        open_db: Opens a database session for each read.
        disconnected: Tells whether the viewer has gone.

    Yields:
        SSE frames, each carrying one event and its id.
    """
    last_sent = time.monotonic()
    woken = asyncio.Event()
    viewers = _viewers.setdefault(session_id, set())
    viewers.add(woken)
    try:
        while True:
            woken.clear()
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
                await asyncio.wait_for(woken.wait(), _POLL_SECONDS)
            if time.monotonic() - last_sent >= _KEEPALIVE_SECONDS:
                last_sent = time.monotonic()
                yield ": keepalive\n\n"
    finally:
        viewers.discard(woken)
        if not viewers and _viewers.get(session_id) is viewers:
            del _viewers[session_id]


def _on_notify(_conn: object, _pid: int, _channel: str, session_id: str) -> None:
    """Wake a session's viewers on a ``NOTIFY`` from any replica."""
    _wake(session_id)


async def run_stream_listener() -> None:
    """Listen for appends on PostgreSQL, waking this process's viewers.

    Runs for the life of the process on one dedicated connection, reconnecting
    after :data:`_RELISTEN_SECONDS` whenever it is lost. Every viewer is woken
    on each (re)connect, to read whatever was appended while nobody listened.
    Returns at once on SQLite, where the writer wakes viewers itself.
    """
    global _listening
    if is_sqlite_url(DB_URL):
        return
    while True:
        try:
            async with dedicated_engine().connect() as conn:
                pg = (await conn.get_raw_connection()).driver_connection
                assert pg is not None
                lost = asyncio.Event()
                pg.add_termination_listener(lambda _conn, done=lost: done.set())
                await pg.add_listener(STREAM_CHANNEL, _on_notify)
                _listening = True
                _wake_all()
                await lost.wait()
            logger.warning("Session stream listener lost its connection")
        except Exception:
            logger.warning("Session stream listener failed", exc_info=True)
        finally:
            _listening = False
        await asyncio.sleep(_RELISTEN_SECONDS)
