"""Stale-tolerant ADK session services for SQLite and SQLAlchemy databases.

During a single ag_ui_adk invocation the same ADK session is written through
two independent code paths:

1. The ADK ``Runner`` appends events using the session reference it fetched
   at the start of the invocation.
2. ``ag_ui_adk`` writes ``pending_tool_calls`` (and related bookkeeping) on
   every ``ToolCallEndEvent`` / ``ToolCallResultEvent``, using a freshly
   fetched session each time.

Path 2 never updates path 1's reference, so the Runner's view of the session
lags behind storage and the upstream stale-writer checks raise "stale
session" — a false positive, because both writers live in this same process.

The subclasses here refresh the in-flight session's revision from storage
before delegating. That refresh alone is not enough, though: upstream
serializes appends for a logical session behind an in-process ``asyncio.Lock``
and only re-reads the storage revision *inside* that lock, while our refresh
reads it in a separate transaction *before* acquiring the lock. A concurrent
writer (e.g. the Runner resuming a human-approved plan) can commit in that
window, advancing the revision so the refreshed value is already stale by the
time upstream checks it. We therefore wrap the delegated append in a retry
loop: the stale check fires before any write and rolls back, so re-syncing the
revision and retrying is safe and converges once the competing writer finishes.
"""

import asyncio

from google.adk.events.event import Event
from google.adk.sessions.database_session_service import (
    _STALE_SESSION_ERROR_MESSAGE,
    DatabaseSessionService,
)
from google.adk.sessions.session import Session
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from sqlalchemy import select

# Upper bound on stale-retry attempts. Contention during a single invocation is
# limited to the handful of events the Runner and ag_ui_adk append concurrently,
# so a small budget converges; the cap guards against an unexpected hot loop.
_MAX_STALE_APPEND_ATTEMPTS = 8


class StaleTolerantSqliteSessionService(SqliteSessionService):
    """SqliteSessionService that refreshes the in-flight session timestamp
    instead of raising on a stale ``last_update_time``.

    See the module docstring for why the upstream stale check is a false
    positive in this application, and why a single pre-read is not enough.
    """

    async def _refresh_last_update_time(self, session: Session) -> None:
        """Sync ``session.last_update_time`` up to the value in storage."""
        async with (
            self._get_db_connection() as db,
            db.execute(
                "SELECT update_time FROM sessions WHERE app_name=? AND"
                " user_id=? AND id=?",
                (session.app_name, session.user_id, session.id),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            if row is not None and row["update_time"] > session.last_update_time:
                session.last_update_time = row["update_time"]

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return await super().append_event(session=session, event=event)
        for attempt in range(_MAX_STALE_APPEND_ATTEMPTS):
            await self._refresh_last_update_time(session)
            try:
                return await super().append_event(session=session, event=event)
            except ValueError as exc:
                if (
                    "stale session" not in str(exc).lower()
                    or attempt == _MAX_STALE_APPEND_ATTEMPTS - 1
                ):
                    raise
                # Yield so the competing in-process writer can commit before we
                # re-read the storage revision and retry.
                await asyncio.sleep(0)
        raise AssertionError("unreachable")  # pragma: no cover


class StaleTolerantDatabaseSessionService(DatabaseSessionService):
    """DatabaseSessionService (PostgreSQL etc.) that refreshes the in-flight
    session revision instead of raising on a stale writer.

    The upstream check compares ``session._storage_update_marker`` (and, for
    marker-less sessions, ``last_update_time``) against storage and raises on
    mismatch. Before delegating, this subclass syncs both fields from storage;
    because upstream re-reads the revision inside its per-session lock, the
    sync can still lose a race with a concurrent committer, so the append is
    retried on the stale error (see module docstring).

    This relies on private google-adk APIs (``_get_schema_classes``,
    ``_rollback_on_exception_session``, ``Session._storage_update_marker``,
    ``_STALE_SESSION_ERROR_MESSAGE``) — the same coupling level as
    ``StaleTolerantSqliteSessionService``'s use of ``_get_db_connection``.
    Re-check on google-adk upgrades.
    """

    async def _refresh_revision(self, session: Session) -> None:
        """Sync ``last_update_time`` and ``_storage_update_marker`` from storage."""
        await self._prepare_tables()  # type: ignore[no-untyped-call]
        schema = self._get_schema_classes()
        is_sqlite = self.db_engine.dialect.name == "sqlite"
        async with self._rollback_on_exception_session(read_only=True) as sql_session:
            stmt = (
                select(schema.StorageSession)
                .filter(schema.StorageSession.app_name == session.app_name)
                .filter(schema.StorageSession.user_id == session.user_id)
                .filter(schema.StorageSession.id == session.id)
            )
            result = await sql_session.execute(stmt)
            storage_session = result.scalars().one_or_none()
            if storage_session is not None:
                session.last_update_time = storage_session.get_update_timestamp(
                    is_sqlite
                )
                session._storage_update_marker = storage_session.get_update_marker()

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return await super().append_event(session=session, event=event)
        for attempt in range(_MAX_STALE_APPEND_ATTEMPTS):
            await self._refresh_revision(session)
            try:
                return await super().append_event(session=session, event=event)
            except ValueError as exc:
                if (
                    str(exc) != _STALE_SESSION_ERROR_MESSAGE
                    or attempt == _MAX_STALE_APPEND_ATTEMPTS - 1
                ):
                    raise
                # Yield so the competing in-process writer can commit before we
                # re-read the storage revision and retry.
                await asyncio.sleep(0)
        raise AssertionError("unreachable")  # pragma: no cover
