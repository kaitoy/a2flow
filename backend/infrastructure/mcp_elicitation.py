"""Putting an MCP server's mid-call question to the run's initiator, and waiting.

An MCP server may stop partway through ``tools/call`` and ask the client
something (``elicitation/create``). When it does during a workflow run,
:class:`SqlElicitationBroker` is what answers on A2Flow's side:

1. records the question as an :class:`models.mcp_elicitation.MCPElicitation`
   row, open until ``MCP_ELICITATION_TIMEOUT_SECONDS`` from now;
2. shows it in the session's chat, by appending an ``ACTIVITY_SNAPSHOT`` event
   (``activityType: "mcp_elicitation"``) to the turn the call is running in --
   the same stream every viewer already reads, on any replica;
3. polls the row until the answer lands -- written by whichever replica the
   answering request reached -- or the question expires.

Only the run's initiator may answer, and nobody is notified here: only a tool a
task binds with ``elicits`` may ask (:meth:`infrastructure.mcp_gateway.McpGateway.call_tool`),
and such a task starts only on a turn the initiator drove from the chat -- they
were notified before it started
(:func:`infrastructure.workflow_task_tools.update_workflow_task`) and are
looking at the chat the question appears in.

The tool call, and with it the turn, stays open the whole time. The caller
(:mod:`infrastructure.mcp_client`) pauses its own timeout for the wait, so the
expiry here is what bounds it -- the case of an initiator who resumed the task
and then walked away.

Only form-mode questions are put to a person. A URL-mode one -- "go to this
page" -- is declined: nothing here could tell when the person was done.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

from ag_ui.core import ActivitySnapshotEvent
from mcp import types
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure import database
from models.mcp_elicitation import (
    MCPElicitation,
    MCPElicitationCreate,
    MCPElicitationStatus,
)
from repositories.execution_session import SqlExecutionSessionRepository
from repositories.mcp_elicitation import SqlMCPElicitationRepository
from repositories.session_stream import SessionStreamRepository
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from services.session_stream import notify_viewers, serialize

logger = logging.getLogger(__name__)

#: The ``activityType`` a question is shown in the chat under.
ELICITATION_ACTIVITY_TYPE = "mcp_elicitation"

#: How often the waiting side re-reads the question. The answer may land on
#: another replica, so nothing can wake this one; a second is well under the
#: time it takes a person to notice their answer took effect.
_POLL_SECONDS = 1.0

#: What a question that ended without an answer reads as to the server.
_NO_ANSWER = types.ElicitResult(action="cancel")

#: The server's answer for each way a person can close a question.
_ACTIONS: dict[MCPElicitationStatus, Literal["accept", "decline", "cancel"]] = {
    MCPElicitationStatus.accepted: "accept",
    MCPElicitationStatus.declined: "decline",
    MCPElicitationStatus.cancelled: "cancel",
}


@asynccontextmanager
async def _default_session() -> AsyncIterator[AsyncSession]:
    """Open a database session on the module-level engine.

    Yields:
        A fresh ``AsyncSession``.
    """
    async with AsyncSession(database.engine) as db:
        yield db


def to_elicit_result(row: MCPElicitation) -> types.ElicitResult:
    """Return what a closed question tells the server.

    Args:
        row: A question no longer ``pending``.

    Returns:
        ``accept`` with the submitted values, ``decline``, or ``cancel`` -- the
        last also for an expired question, which nobody answered.
    """
    action = _ACTIONS.get(row.status)
    if action is None:
        return _NO_ANSWER
    if action == "accept":
        return types.ElicitResult(action="accept", content=row.content or {})
    return types.ElicitResult(action=action)


def _as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as an aware UTC instant; SQLite hands back naive ones.

    Args:
        dt: A stored instant.

    Returns:
        The same instant, timezone-aware.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SqlElicitationBroker:
    """Puts a server's question to the run's initiator through the database."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
        | None = None,
        poll_seconds: float = _POLL_SECONDS,
    ) -> None:
        """Initialize the broker.

        Args:
            session_factory: Opens the short database sessions each step runs
                on. Defaults to a session on the module-level engine.
            poll_seconds: How often to re-read the question while waiting.
        """
        self._session_factory = session_factory or _default_session
        self._poll_seconds = poll_seconds

    async def elicit(
        self,
        *,
        tenant_id: str,
        execution_id: str,
        session_id: str,
        user_id: str | None,
        server_id: str,
        server_name: str,
        tool_name: str,
        params: types.ElicitRequestParams,
    ) -> types.ElicitResult:
        """Ask the run's initiator, and return their answer once given.

        Args:
            tenant_id: Tenant the run belongs to.
            execution_id: The run whose tool call asked.
            session_id: The session (chat) the call runs in.
            user_id: The user the turn acts for, recorded as the question's
                creator; the initiator when unknown.
            server_id: Id of the registered server that asked.
            server_name: Its name, shown in the chat.
            tool_name: The tool whose call asked.
            params: The server's ``elicitation/create`` parameters.

        Returns:
            The answer for the server: ``accept`` with the submitted values,
            ``decline``, or ``cancel`` -- which is also what an unanswered,
            expired question reads as.
        """
        if not isinstance(params, types.ElicitRequestFormParams):
            logger.info("Declined a URL-mode question from %s", server_name)
            return types.ElicitResult(action="decline")
        asked: list[str] = []
        try:
            row_id = await self._ask(
                asked,
                tenant_id=tenant_id,
                execution_id=execution_id,
                session_id=session_id,
                user_id=user_id,
                data=MCPElicitationCreate(
                    workflow_execution_id=execution_id,
                    session_id=session_id,
                    mcp_server_id=server_id,
                    server_name=server_name,
                    tool_name=tool_name,
                    message=params.message,
                    requested_schema=params.requestedSchema,
                    expires_at=datetime.now(UTC)
                    + timedelta(seconds=get_settings().mcp_elicitation_timeout_seconds),
                ),
            )
            if row_id is None:
                return _NO_ANSWER
            return await self._wait(tenant_id, row_id)
        except asyncio.CancelledError:
            # The turn stopped, possibly while the question was still being
            # announced; nobody may answer a question nobody waits on.
            for created in asked:
                await asyncio.shield(self._expire(tenant_id, created))
            raise

    async def _ask(
        self,
        asked: list[str],
        *,
        tenant_id: str,
        execution_id: str,
        session_id: str,
        user_id: str | None,
        data: MCPElicitationCreate,
    ) -> str | None:
        """Record the question and show it in the chat.

        Args:
            asked: Receives the question's id the moment it is stored, so a
                caller cancelled while the question is still being announced
                can still close it.
            tenant_id: Tenant the run belongs to.
            execution_id: The run whose tool call asked.
            session_id: The session (chat) the call runs in.
            user_id: The user the turn acts for, if known.
            data: The question.

        Returns:
            The question's id, or ``None`` when the run no longer exists.
        """
        async with self._session_factory() as db:
            execution = await SqlWorkflowExecutionRepository(
                db, tenant_id=tenant_id
            ).get(execution_id)
            if execution is None:
                return None
            actor = user_id or execution.initiator_id
            row = await SqlMCPElicitationRepository(db, tenant_id=tenant_id).create(
                data, user_id=actor
            )
            row_id = row.id
            asked.append(row_id)
            session = await SqlExecutionSessionRepository(db, tenant_id=tenant_id).get(
                session_id
            )
            if session is not None and session.active_run_id is not None:
                event = ActivitySnapshotEvent(
                    message_id=row_id,
                    activity_type=ELICITATION_ACTIVITY_TYPE,
                    content={
                        "elicitationId": row_id,
                        "sessionId": session_id,
                        "executionId": execution_id,
                    },
                )
                await SessionStreamRepository(db).append(
                    session_id, session.active_run_id, [serialize(event)]
                )
                notify_viewers()
            return row_id

    async def _wait(self, tenant_id: str, row_id: str) -> types.ElicitResult:
        """Poll the question until it closes or expires.

        Args:
            tenant_id: Tenant the run belongs to.
            row_id: The question's id.

        Returns:
            The answer for the server.
        """
        while True:
            await asyncio.sleep(self._poll_seconds)
            async with self._session_factory() as db:
                repo = SqlMCPElicitationRepository(db, tenant_id=tenant_id)
                row = await repo.get(row_id)
                if row is None:
                    return _NO_ANSWER
                if row.status is not MCPElicitationStatus.pending:
                    return to_elicit_result(row)
                now = datetime.now(UTC)
                if now < _as_utc(row.expires_at):
                    continue
                if await repo.expire(row_id, user_id=row.created_by, now=now):
                    return _NO_ANSWER
                # An answer landed between the read and the expiry: it wins.
                answered = await repo.get(row_id)
                return _NO_ANSWER if answered is None else to_elicit_result(answered)

    async def _expire(self, tenant_id: str, row_id: str) -> None:
        """Close a question nobody is waiting on any more.

        Args:
            tenant_id: Tenant the run belongs to.
            row_id: The question's id.
        """
        try:
            async with self._session_factory() as db:
                repo = SqlMCPElicitationRepository(db, tenant_id=tenant_id)
                row = await repo.get(row_id)
                if row is not None:
                    await repo.expire(
                        row_id, user_id=row.created_by, now=datetime.now(UTC)
                    )
        except Exception:  # noqa: BLE001 -- best effort on the way out
            logger.exception("Failed to expire abandoned question %s", row_id)


@lru_cache(maxsize=1)
def get_elicitation_broker() -> SqlElicitationBroker:
    """Return the process-wide broker.

    Returns:
        The shared broker on the module-level engine.
    """
    return SqlElicitationBroker()
