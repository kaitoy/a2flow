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
before delegating, so the Runner's appends proceed.
"""

from google.adk.events.event import Event
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.sessions.session import Session
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from sqlalchemy import select


class StaleTolerantSqliteSessionService(SqliteSessionService):
    """SqliteSessionService that refreshes the in-flight session timestamp
    instead of raising on a stale ``last_update_time``.

    See the module docstring for why the upstream stale check is a false
    positive in this application.
    """

    async def append_event(self, session: Session, event: Event) -> Event:
        if not event.partial:
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
        return await super().append_event(session=session, event=event)


class StaleTolerantDatabaseSessionService(DatabaseSessionService):
    """DatabaseSessionService (PostgreSQL etc.) that refreshes the in-flight
    session revision instead of raising on a stale writer.

    The upstream check compares ``session._storage_update_marker`` (and, for
    marker-less sessions, ``last_update_time``) against storage and raises on
    mismatch. Before delegating, this subclass syncs both fields from storage
    so a same-process second writer (see module docstring) cannot abort the
    Runner's appends.

    This relies on private google-adk APIs (``_get_schema_classes``,
    ``_rollback_on_exception_session``, ``Session._storage_update_marker``) —
    the same coupling level as ``StaleTolerantSqliteSessionService``'s use of
    ``_get_db_connection``. Re-check on google-adk upgrades.
    """

    async def append_event(self, session: Session, event: Event) -> Event:
        if not event.partial:
            await self._prepare_tables()  # type: ignore[no-untyped-call]
            schema = self._get_schema_classes()
            is_sqlite = self.db_engine.dialect.name == "sqlite"
            async with self._rollback_on_exception_session(
                read_only=True
            ) as sql_session:
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
        return await super().append_event(session=session, event=event)
