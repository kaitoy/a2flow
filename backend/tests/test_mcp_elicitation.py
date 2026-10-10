"""Tests for putting an MCP server's mid-call question to a run's initiator.

Two halves, meeting in the ``mcp_elicitations`` table: the broker the waiting
tool call runs (:mod:`infrastructure.mcp_elicitation`) and the routes the
person answers through (:mod:`services.mcp_elicitation`). Both run against the
same database, so an answer posted through the API is what the broker's poll
picks up -- as it would be across two replicas.

That database is a file rather than the suite's usual in-memory one. The
in-memory engine shares a single connection between every session, and here two
genuinely run at once -- the broker's poll and the answering request -- so one
closing would roll back the other's uncommitted write. Separate connections are
what production has, and what this module needs to observe it.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from mcp import types
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_elicitation import (
    ELICITATION_ACTIVITY_TYPE,
    SqlElicitationBroker,
)
from models.execution_session import ExecutionSession, SessionStreamEvent
from models.mcp_elicitation import MCPElicitation, MCPElicitationStatus
from models.notification import Notification
from tests import test_workflow_execution_access as _access
from tests._engine import _set_sqlite_fk, pg_url
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests.test_workflow_execution_access import (
    ADMIN,
    APPROVER,
    OWNER,
    SUPER_ADMIN,
    UNRELATED,
    _insert_approval,
    _seed_session,
)

#: The API client and engine fixture of the run access tests, reused as is.
access_env = _access.access_env


@pytest.fixture(autouse=True)
def _separate_connections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Back ``access_env`` with a file database, one connection per session."""
    if pg_url() is not None:
        return

    async def _file_engine() -> AsyncEngine:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        sa_event.listen(engine.sync_engine, "connect", _set_sqlite_fk)
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        return engine

    monkeypatch.setattr(_access, "make_test_engine", _file_engine)


#: The question the Azure MCP Server asks before touching a secret.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "oneOf": [
                {"const": "accept", "title": "Approve"},
                {"const": "reject", "title": "Reject"},
            ],
        }
    },
    "required": ["decision"],
}
QUESTION = types.ElicitRequestFormParams(
    message="Do you want to continue?", requestedSchema=SCHEMA
)

Env = tuple[AsyncClient, AsyncEngine]


def _broker(eng: AsyncEngine) -> SqlElicitationBroker:
    """A broker on the test engine that polls fast."""

    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(eng) as db:
            yield db

    return SqlElicitationBroker(session_factory=_session, poll_seconds=0.02)


async def _elicit(
    eng: AsyncEngine,
    execution_id: str,
    params: types.ElicitRequestParams = QUESTION,
) -> types.ElicitResult:
    """Ask the question the way the gateway does for a run's call."""
    return await _broker(eng).elicit(
        tenant_id=DEFAULT_TEST_TENANT_ID,
        execution_id=execution_id,
        session_id="sess-1",
        user_id="owner",
        server_id="srv-azure",
        server_name="Azure MCP Server",
        tool_name="keyvault_secret_create",
        params=params,
    )


async def _eventually(eng: AsyncEngine, model: Any) -> list[Any]:
    """Wait until the broker has written at least one row of ``model``.

    The broker runs in its own task, so a test that has seen the question
    stored may still be ahead of the announcement that follows it. Generous,
    because the whole suite runs in parallel.
    """
    for _ in range(500):
        async with AsyncSession(eng) as db:
            rows = list((await db.exec(select(model))).all())
        if rows:
            return rows
        await asyncio.sleep(0.02)
    raise AssertionError(f"the broker never wrote a {model.__name__}")


async def _pending(eng: AsyncEngine) -> MCPElicitation:
    """Wait until the broker has recorded its question, and return it."""
    (row,) = await _eventually(eng, MCPElicitation)
    assert isinstance(row, MCPElicitation)
    return row


async def _insert_question(
    eng: AsyncEngine,
    execution_id: str,
    *,
    expires_at: datetime | None = None,
) -> str:
    """Insert an open question directly, and return its id."""
    async with AsyncSession(eng) as db:
        row = MCPElicitation(
            workflow_execution_id=execution_id,
            session_id="sess-1",
            mcp_server_id="srv-azure",
            server_name="Azure MCP Server",
            tool_name="keyvault_secret_create",
            message=QUESTION.message,
            requested_schema=SCHEMA,
            expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        row_id = row.id
        db.add(row)
        await db.commit()
        return row_id


def _url(execution_id: str, elicitation_id: str) -> str:
    """URL of one question asked in the seeded main session."""
    return (
        f"/api/v1/workflow-executions/{execution_id}/sessions/sess-1"
        f"/elicitations/{elicitation_id}"
    )


_APPROVE = {"action": "accept", "content": {"decision": "accept"}}


# ---------- the waiting side ----------


async def test_an_accepted_answer_reaches_the_waiting_call(access_env: Env) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    waiting = asyncio.create_task(_elicit(eng, execution_id))

    question = await _pending(eng)
    assert question.status is MCPElicitationStatus.pending
    assert question.requested_schema == SCHEMA
    res = await client.post(
        _url(execution_id, question.id) + "/answer", json=_APPROVE, headers=OWNER
    )
    assert assert_ok(res)["status"] == "accepted"

    result = await asyncio.wait_for(waiting, timeout=5)
    assert result.action == "accept"
    assert result.content == {"decision": "accept"}


async def test_a_decline_reaches_the_waiting_call(access_env: Env) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    waiting = asyncio.create_task(_elicit(eng, execution_id))

    question = await _pending(eng)
    await client.post(
        _url(execution_id, question.id) + "/answer",
        json={"action": "decline"},
        headers=OWNER,
    )

    result = await asyncio.wait_for(waiting, timeout=5)
    assert result.action == "decline"
    assert result.content is None


async def test_the_question_is_shown_in_the_running_turn(access_env: Env) -> None:
    """Appended to the turn's stream, which every viewer already reads."""
    _, eng = access_env
    execution_id = await _seed_session(eng)
    async with AsyncSession(eng) as db:
        session = await db.get(ExecutionSession, "sess-1")
        assert session is not None
        session.active_run_id = "run-1"
        db.add(session)
        await db.commit()
    waiting = asyncio.create_task(_elicit(eng, execution_id))

    question = await _pending(eng)
    events = await _eventually(eng, SessionStreamEvent)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert [(e.run_id, e.payload["activityType"]) for e in events] == [
        ("run-1", ELICITATION_ACTIVITY_TYPE)
    ]
    assert events[0].payload["messageId"] == question.id
    assert events[0].payload["content"] == {
        "elicitationId": question.id,
        "sessionId": "sess-1",
        "executionId": execution_id,
    }


async def test_asking_notifies_nobody(access_env: Env) -> None:
    """The initiator was notified before the task started, and is in the chat."""
    _, eng = access_env
    execution_id = await _seed_session(eng)
    waiting = asyncio.create_task(_elicit(eng, execution_id))

    await _pending(eng)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    async with AsyncSession(eng) as db:
        assert (await db.exec(select(Notification))).all() == []


async def test_an_unanswered_question_expires_as_a_cancel(
    access_env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, eng = access_env
    monkeypatch.setenv("MCP_ELICITATION_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    try:
        execution_id = await _seed_session(eng)
        result = await asyncio.wait_for(_elicit(eng, execution_id), timeout=5)
    finally:
        get_settings.cache_clear()

    assert result.action == "cancel"
    question = await _pending(eng)
    assert question.status is MCPElicitationStatus.expired
    res = await client.post(
        _url(execution_id, question.id) + "/answer", json=_APPROVE, headers=OWNER
    )
    assert_err(res, "ELICITATION_ALREADY_ANSWERED", 409)


async def test_a_question_nobody_waits_on_any_more_expires(access_env: Env) -> None:
    """The turn stopped: an answer would reach nothing, so none is taken."""
    _, eng = access_env
    execution_id = await _seed_session(eng)
    waiting = asyncio.create_task(_elicit(eng, execution_id))

    await _pending(eng)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    question = await _pending(eng)
    assert question.status is MCPElicitationStatus.expired


async def test_a_url_question_is_declined_without_asking(access_env: Env) -> None:
    _, eng = access_env
    execution_id = await _seed_session(eng)

    result = await _elicit(
        eng,
        execution_id,
        types.ElicitRequestURLParams(
            message="Sign in", url="https://example.com", elicitationId="e-1"
        ),
    )

    assert result.action == "decline"
    async with AsyncSession(eng) as db:
        assert (await db.exec(select(MCPElicitation))).first() is None


# ---------- the answering side ----------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(APPROVER, id="approver"),
        pytest.param(SUPER_ADMIN, id="super_admin"),
        pytest.param(ADMIN, id="admin"),
        pytest.param(UNRELATED, id="unrelated"),
    ],
)
async def test_only_the_initiator_may_answer(
    access_env: Env, headers: dict[str, str]
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    question_id = await _insert_question(eng, execution_id)

    res = await client.post(
        _url(execution_id, question_id) + "/answer", json=_APPROVE, headers=headers
    )

    assert_err(res, "FORBIDDEN", 403)


async def test_an_answer_that_does_not_fit_the_form_is_refused(
    access_env: Env,
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    question_id = await _insert_question(eng, execution_id)

    res = await client.post(
        _url(execution_id, question_id) + "/answer",
        json={"action": "accept", "content": {"decision": "maybe"}},
        headers=OWNER,
    )

    assert_err(res, "INVALID_SESSION_INPUT", 422)


async def test_a_question_is_answered_once(access_env: Env) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    question_id = await _insert_question(eng, execution_id)
    url = _url(execution_id, question_id) + "/answer"

    first = await client.post(url, json=_APPROVE, headers=OWNER)
    second = await client.post(url, json={"action": "decline"}, headers=OWNER)

    answered = assert_ok(first)
    assert answered["status"] == "accepted"
    assert answered["answeredBy"] == "owner"
    assert answered["content"] == {"decision": "accept"}
    assert_err(second, "ELICITATION_ALREADY_ANSWERED", 409)


async def test_an_expired_question_cannot_be_answered(access_env: Env) -> None:
    """Even before the waiting side has noticed the expiry."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    question_id = await _insert_question(
        eng, execution_id, expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )

    res = await client.post(
        _url(execution_id, question_id) + "/answer", json=_APPROVE, headers=OWNER
    )

    assert_err(res, "ELICITATION_ALREADY_ANSWERED", 409)


async def test_a_question_from_another_session_is_not_found(access_env: Env) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    question_id = await _insert_question(eng, execution_id)

    res = await client.get(
        f"/api/v1/workflow-executions/{execution_id}/sessions/sess-other"
        f"/elicitations/{question_id}",
        headers=OWNER,
    )

    assert_err(res, "NOT_FOUND", 404)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(OWNER, id="owner"),
        pytest.param(APPROVER, id="approver"),
        pytest.param(ADMIN, id="admin"),
    ],
)
async def test_anyone_who_may_read_the_run_may_read_its_questions(
    access_env: Env, headers: dict[str, str]
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    question_id = await _insert_question(eng, execution_id)

    res = await client.get(_url(execution_id, question_id), headers=headers)

    question = assert_ok(res)
    assert question["status"] == "pending"
    assert question["requestedSchema"] == SCHEMA
    assert question["expiresAt"].endswith("Z")


async def test_an_unrelated_user_cannot_read_a_question(access_env: Env) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    question_id = await _insert_question(eng, execution_id)

    res = await client.get(_url(execution_id, question_id), headers=UNRELATED)

    assert_err(res, "FORBIDDEN", 403)
