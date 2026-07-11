"""Cross-process mutual exclusion, used to keep one ADK session to one driver.

A horizontally scaled backend runs the same ADK session from two processes
whenever two ``POST /agent`` requests for one ``thread_id`` land on different
replicas — a human-in-the-loop resume racing the tail of the run that requested
it, or the same conversation driven from two browser tabs.

The database survives that race on its own. google-adk's
``DatabaseSessionService.append_event`` takes ``SELECT ... FOR UPDATE`` on the
``sessions`` row for the whole append transaction on PostgreSQL, so appends to
one session are already serialized across processes and neither the session
state nor the event rows can be lost. What is *not* protected is the reader: the
ADK ``Runner`` holds a single in-memory ``Session`` for the length of an
invocation, so events another replica appends during that window never reach it,
and the rest of the run reasons over a conversation that is missing them.

Serializing appends cannot repair a stale reader — only keeping a session to one
driver at a time can. So the lock here is taken at the *run* level: the agent
endpoint holds it for the whole SSE stream, and a second concurrent run of the
same session is rejected outright rather than left to diverge quietly.

On PostgreSQL the lock is a session-level advisory lock
(``pg_try_advisory_lock``) on a dedicated connection from a private ``NullPool``
engine. ``NullPool`` earns its place twice: an agent run outlives the request
that started it, so borrowing from the request-serving pool for minutes at a
time would starve it, and a session-level advisory lock is released when its
connection closes — on a *pooled* connection a missed unlock would instead leak
the lock for the life of that pooled connection. The engine runs in
``AUTOCOMMIT`` so the held connection never sits idle-in-transaction.

This does mean the deployment must not put a transaction-pooling proxy (e.g.
PgBouncer in ``transaction`` mode) between the app and PostgreSQL: session-level
advisory locks need session-level pooling to survive between statements.

SQLite deployments are single-process by construction, so there the same
guarantee comes from an in-process :class:`asyncio.Lock` keyed the same way.
"""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from infrastructure.database import ASYNC_DB_URL, is_sqlite_url

logger = logging.getLogger(__name__)

#: How long to keep retrying a contended lock before giving up. A client that
#: aborts a run and immediately starts another (a reload mid-stream) can arrive
#: while the abandoned stream's teardown is still unwinding; a short wait
#: absorbs that hand-off instead of rejecting a legitimate retry.
_DEFAULT_WAIT_SECONDS = 5.0

#: Delay between ``pg_try_advisory_lock`` attempts while waiting. Polling rather
#: than blocking in ``pg_advisory_lock`` keeps the wait bounded and cancellable
#: without parking a PostgreSQL backend in an open-ended lock wait.
_POLL_INTERVAL_SECONDS = 0.1

#: In-process locks for the SQLite path, keyed by ``(event loop id, lock key)``.
#: The loop id keeps locks from leaking across the fresh event loop each test
#: gets, which an :class:`asyncio.Lock` would reject as bound to another loop.
_local_locks: dict[tuple[int, str], asyncio.Lock] = {}
_local_waiters: dict[tuple[int, str], int] = {}


class LockNotAcquiredError(Exception):
    """Raised when a lock is still held elsewhere once the wait has elapsed."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"lock {key!r} is held by another holder")


def agent_run_key(app_name: str, user_id: str, session_id: str) -> str:
    """Build the lock key identifying one logical ADK session's agent run.

    Args:
        app_name: The ADK application name.
        user_id: Id of the user the session belongs to.
        session_id: The ADK session id (the AG-UI ``thread_id``).

    Returns:
        The colon-joined key to pass to :func:`advisory_lock`.
    """
    return f"{app_name}:{user_id}:{session_id}"


def lock_id(key: str) -> int:
    """Hash a lock key into the signed 64-bit integer ``pg_advisory_lock`` takes.

    BLAKE2b rather than :func:`hash`, whose output is salted per process by
    ``PYTHONHASHSEED``: replicas would derive different ids for the same key and
    never contend. For the same reason the digest must stay stable — changing it
    splits the lock across a rolling deploy, letting an old and a new pod drive
    one session at once.

    Args:
        key: The lock key, e.g. from :func:`agent_run_key`.

    Returns:
        The key's BLAKE2b digest as a signed 64-bit integer.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


@lru_cache(maxsize=1)
def _lock_engine() -> AsyncEngine:
    """Return the private NullPool/AUTOCOMMIT engine advisory locks are taken on.

    See the module docstring for why locks get their own engine rather than
    borrowing a connection from the request-serving pool.
    """
    return create_async_engine(
        ASYNC_DB_URL,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        echo=False,
    )


async def _try_acquire(conn: AsyncConnection, key_id: int, wait_seconds: float) -> bool:
    """Poll ``pg_try_advisory_lock`` until it succeeds or ``wait_seconds`` elapses."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    stmt = text("SELECT pg_try_advisory_lock(:key_id)")
    while True:
        if bool(await conn.scalar(stmt, {"key_id": key_id})):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def _postgres_advisory_lock(key: str, wait_seconds: float) -> AsyncIterator[None]:
    """Hold a PostgreSQL session-level advisory lock for the body's duration."""
    key_id = lock_id(key)
    async with _lock_engine().connect() as conn:
        if not await _try_acquire(conn, key_id, wait_seconds):
            raise LockNotAcquiredError(key)
        try:
            yield
        finally:
            # Closing the connection releases the lock regardless (NullPool hands
            # back a real close), so a failed unlock here is recoverable noise
            # rather than a leak — never let it displace the error that got us
            # into this teardown.
            try:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:key_id)"), {"key_id": key_id}
                )
            except Exception:
                logger.warning(
                    "Failed to release advisory lock %r; falling back to "
                    "releasing it by closing the connection.",
                    key,
                    exc_info=True,
                )


@asynccontextmanager
async def _in_process_lock(key: str, wait_seconds: float) -> AsyncIterator[None]:
    """Hold an in-process :class:`asyncio.Lock` for the body's duration.

    The SQLite stand-in for the advisory lock. Reads and writes of the registry
    below never span an ``await``, so the event loop cannot interleave another
    task between them and no guard lock is needed.
    """
    map_key = (id(asyncio.get_running_loop()), key)
    lock = _local_locks.get(map_key)
    if lock is None:
        lock = asyncio.Lock()
        _local_locks[map_key] = lock
    _local_waiters[map_key] = _local_waiters.get(map_key, 0) + 1
    try:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=wait_seconds)
        except TimeoutError as exc:
            raise LockNotAcquiredError(key) from exc
        try:
            yield
        finally:
            lock.release()
    finally:
        # Drop the registry entry once the last holder and waiter are gone, so a
        # long-lived process does not accumulate one lock per session forever.
        remaining = _local_waiters[map_key] - 1
        if remaining <= 0:
            del _local_waiters[map_key]
            del _local_locks[map_key]
        else:
            _local_waiters[map_key] = remaining


@asynccontextmanager
async def advisory_lock(
    key: str, *, wait_seconds: float | None = None
) -> AsyncIterator[None]:
    """Hold the lock named ``key`` for the duration of the ``async with`` body.

    Backed by a PostgreSQL session-level advisory lock, or by an in-process
    :class:`asyncio.Lock` when ``DB_URL`` selects SQLite (see the module
    docstring).

    Args:
        key: The lock key; the same key contends across processes.
        wait_seconds: How long to keep retrying a contended lock before giving
            up. Resolved against :data:`_DEFAULT_WAIT_SECONDS` at call time —
            rather than bound as a default argument — so the wait stays tunable
            in one place for callers that take it as given.

    Yields:
        ``None``, with the lock held.

    Raises:
        LockNotAcquiredError: The lock was still held elsewhere after
            ``wait_seconds``.
    """
    wait = _DEFAULT_WAIT_SECONDS if wait_seconds is None else wait_seconds
    if is_sqlite_url(ASYNC_DB_URL):
        async with _in_process_lock(key, wait):
            yield
    else:
        async with _postgres_advisory_lock(key, wait):
            yield
