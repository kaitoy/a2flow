"""Tests for the server side of a workflow session: kickoff, pause, and resume.

A run is executed through the API, then its turns are driven by calling
:meth:`services.session_runner.SessionRunner.run_turn` directly -- the
dispatcher loop only decides *when* to call it. The ADK agent is a scripted
stand-in that records the input of every turn and replays AG-UI events, so
these tests pin down what the runner sends and how it reads what comes back.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from ag_ui.core import (
    EventType,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolMessage,
    UserMessage,
)
from google.adk.sessions import InMemorySessionService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.context import APP_NAME
from infrastructure.agent import tenant_app_name
from infrastructure.locks import advisory_lock, agent_run_key
from models.approval import Approval, ApprovalStatus
from models.execution_session import ExecutionSession, ExecutionSessionStatus
from services.session_inputs import EXECUTION_KICKOFF_PROMPT, RECOVERY_PROMPT
from services.session_runner import SessionRunner
from tests._envelope import assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_published_workflow, create_skill


class ScriptedAgent:
    """Stands in for an ADKAgent: records each turn's input, replays one script per turn."""

    def __init__(self, *scripts: list[Any]) -> None:
        self.scripts = list(scripts)
        self.inputs: list[RunAgentInput] = []

    async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
        self.inputs.append(input_data)
        for event in self.scripts.pop(0) if self.scripts else _finished():
            yield event


def _finished() -> list[Any]:
    return [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]


def _asks_for_approval(approval_id: str, call_id: str = "adk-1") -> list[Any]:
    """A turn that ends paused on ``render_approval`` for ``approval_id``."""
    return [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id=call_id,
            tool_call_name="render_approval",
        ),
        ToolCallArgsEvent(
            type=EventType.TOOL_CALL_ARGS,
            tool_call_id=call_id,
            delta=json.dumps({"approvalId": approval_id}),
        ),
        ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=call_id),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]


@pytest.fixture()
def runner_env(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    real_session_service: InMemorySessionService,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock]:
    """The API client, its engine, a runner over the same database, and the agent registry."""
    client, engine = workflow_client_with_engine
    monkeypatch.setattr("infrastructure.database.engine", engine)
    runner = SessionRunner(
        registry=mock_agent_registry,
        skills_store=mock_skill_manager,
        session_service=real_session_service,
        app_name=APP_NAME,
    )
    return client, engine, runner, mock_agent_registry


async def _execute(client: AsyncClient) -> dict[str, Any]:
    skill = await create_skill(client)
    wf = await create_published_workflow(client, skill["id"])
    execution: dict[str, Any] = assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    return execution


async def _session(engine: AsyncEngine, session_id: str) -> ExecutionSession:
    async with AsyncSession(engine) as db:
        row = await db.get(ExecutionSession, session_id)
    assert row is not None
    return row


async def _insert_approval(engine: AsyncEngine, execution_id: str) -> str:
    async with AsyncSession(engine) as db:
        approval = Approval(
            workflow_execution_id=execution_id,
            title="Go?",
            approver="bob",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="alice",
            updated_by="alice",
        )
        approval_id = approval.id
        db.add(approval)
        await db.commit()
    return approval_id


async def _decide(client: AsyncClient, approval_id: str) -> None:
    assert_ok(
        await client.patch(
            f"/api/v1/approvals/{approval_id}",
            json={"status": "approved"},
            headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
        )
    )


async def test_executing_queues_the_kickoff_on_the_main_session(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, _runner, _registry = runner_env
    execution = await _execute(client)

    row = await _session(engine, execution["sessionId"])
    assert row.status is ExecutionSessionStatus.queued
    assert row.pending_input is not None
    assert row.pending_input["text"] == EXECUTION_KICKOFF_PROMPT


async def test_the_kickoff_runs_on_the_server_with_the_client_tools(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    agent = ScriptedAgent()
    registry.get.return_value = agent

    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    (sent,) = agent.inputs
    assert sent.thread_id == execution["sessionId"]
    assert [m.content for m in sent.messages if isinstance(m, UserMessage)] == [
        EXECUTION_KICKOFF_PROMPT
    ]
    assert {t.name for t in sent.tools} == {"render_approval", "render_a2ui"}
    assert any("A2UI" in c.description for c in sent.context)
    # The run acts as its initiator, whoever queued the turn.
    assert sent.forwarded_props["userId"] == execution["initiatorId"]
    row = await _session(engine, execution["sessionId"])
    assert row.status is ExecutionSessionStatus.idle
    assert row.pending_input is None


async def test_deciding_an_approval_resumes_the_paused_session(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """The decision reaches the run on the server, from whichever screen it was made."""
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    approval_id = await _insert_approval(engine, execution["id"])
    agent = ScriptedAgent(_asks_for_approval(approval_id))
    registry.get.return_value = agent
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    paused = await _session(engine, execution["sessionId"])
    assert paused.status is ExecutionSessionStatus.waiting_for_approval
    assert paused.waiting_on[0]["approval_id"] == approval_id

    await _decide(client, approval_id)
    queued = await _session(engine, execution["sessionId"])
    assert queued.status is ExecutionSessionStatus.queued

    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)
    resumed = agent.inputs[-1]
    results = [m for m in resumed.messages if isinstance(m, ToolMessage)]
    assert [(r.tool_call_id, r.content) for r in results] == [("adk-1", "approved")]
    assert (await _session(engine, execution["sessionId"])).waiting_on == []


async def test_a_decision_made_before_the_controls_appear_is_picked_up(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """Deciding from the approvals list while the requesting turn still runs is not lost."""
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    approval_id = await _insert_approval(engine, execution["id"])
    await _decide(client, approval_id)  # nothing is waiting on it yet

    registry.get.return_value = ScriptedAgent(_asks_for_approval(approval_id))
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    row = await _session(engine, execution["sessionId"])
    assert row.status is ExecutionSessionStatus.queued
    assert row.pending_input is not None
    assert row.pending_input["content"] == ApprovalStatus.approved.value
    assert row.pending_input["sender_id"] == "bob"


async def test_a_turn_cut_off_mid_run_is_resumed_with_the_recovery_prompt(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    async with AsyncSession(engine) as db:
        row = await db.get(ExecutionSession, execution["sessionId"])
        assert row is not None
        row.status = ExecutionSessionStatus.running  # its process died
        db.add(row)
        await db.commit()
    agent = ScriptedAgent()
    registry.get.return_value = agent

    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    (sent,) = agent.inputs
    assert [m.content for m in sent.messages if isinstance(m, UserMessage)] == [
        RECOVERY_PROMPT
    ]


async def test_a_session_someone_else_is_running_is_left_alone(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    agent = ScriptedAgent()
    registry.get.return_value = agent
    key = agent_run_key(
        tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
        execution["initiatorId"],
        execution["sessionId"],
    )

    async with advisory_lock(key):
        await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    assert agent.inputs == []
    assert (await _session(engine, execution["sessionId"])).status is (
        ExecutionSessionStatus.queued
    )


async def test_a_failed_turn_leaves_the_session_in_error(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    registry.get.return_value = ScriptedAgent(
        [RunErrorEvent(type=EventType.RUN_ERROR, message="boom")]
    )

    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    row = await _session(engine, execution["sessionId"])
    assert row.status is ExecutionSessionStatus.error
    assert row.pending_input is None
