from google.adk.events.event import Event
from google.adk.sessions.session import Session
from google.adk.sessions.sqlite_session_service import SqliteSessionService


class StaleTolerantSqliteSessionService(SqliteSessionService):
    """SqliteSessionService that refreshes the in-flight session timestamp
    instead of raising on a stale ``last_update_time``.

    During a single ag_ui_adk invocation the same session is written through
    two independent code paths:

    1. The ADK ``Runner`` appends events using the session reference it
       fetched at the start of the invocation.
    2. ``ag_ui_adk`` writes ``pending_tool_calls`` (and related bookkeeping)
       on every ``ToolCallEndEvent`` / ``ToolCallResultEvent``, using a
       freshly fetched session each time.

    Path 2 never updates path 1's reference, so the Runner's
    ``last_update_time`` lags behind storage. The upstream
    ``SqliteSessionService.append_event`` then raises "stale session" — but
    both writes come from this same process, so the check is a false
    positive that aborts the run. We refresh ``last_update_time`` from
    storage before the upstream check so the Runner's appends proceed.
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
