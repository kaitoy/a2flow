"""Tests for the server side of a workflow session: kickoff, pause, and resume.

A run is executed through the API, then its turns are driven by calling
:meth:`services.session_runner.SessionRunner.run_turn` directly -- the
dispatcher loop only decides *when* to call it. The ADK agent is a scripted
stand-in that records the input of every turn and replays AG-UI events, so
these tests pin down what the runner sends and how it reads what comes back.
"""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

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
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from dependencies.context import APP_NAME
from infrastructure.agent import tenant_app_name
from infrastructure.locks import advisory_lock, agent_run_key
from infrastructure.workflow_task_tools import update_workflow_task, wait_until
from models.approval import Approval, ApprovalStatus
from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.mcp_server import MCPServer, McpTransport
from models.notification import Notification, NotificationType
from models.user import SYSTEM_USER_ID
from models.workflow_execution import WorkflowExecution, WorkflowExecutionStatus
from repositories.execution_session import SqlExecutionSessionRepository
from repositories.execution_session_queue import due_sessions
from services.session_inputs import EXECUTION_KICKOFF_PROMPT, RECOVERY_PROMPT
from services.session_runner import SessionRunner
from tests._envelope import assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import (
    add_template,
    create_published_workflow,
    create_skill,
    generate_workflow,
    publish_workflow,
)


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


# ---------- input, history, and stream over the API ----------


class AppendingAgent(ScriptedAgent):
    """A scripted agent that also persists ADK events, the way ag-ui-adk does mid-turn."""

    def __init__(
        self,
        adk: InMemorySessionService,
        execution: dict[str, Any],
        events: list[Any],
        script: list[Any] | None = None,
    ) -> None:
        super().__init__(*([script] if script is not None else []))
        self.adk = adk
        self.execution = execution
        self.events = events

    async def persist(self) -> None:
        """Append this agent's events to the run's ADK session."""
        key = {
            "app_name": tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
            "user_id": self.execution["initiatorId"],
            "session_id": self.execution["sessionId"],
        }
        session = await self.adk.get_session(**key) or await self.adk.create_session(
            **key
        )
        for event in self.events:
            await self.adk.append_event(session, event)

    async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
        await self.persist()
        async for event in super().run(input_data):
            yield event


def _user_event(text: str) -> Any:
    from google.adk.events.event import Event
    from google.genai import types

    return Event(
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


def _tool_response_event(call_id: str, response: dict[str, Any]) -> Any:
    from google.adk.events.event import Event
    from google.genai import types

    return Event(
        author="tool",
        content=types.Content(
            role="function",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id, name=call_id, response=response
                    )
                )
            ],
        ),
    )


def _base(execution: dict[str, Any]) -> str:
    return (
        f"/api/v1/workflow-executions/{execution['id']}"
        f"/sessions/{execution['sessionId']}"
    )


async def test_a_message_runs_as_its_sender_and_is_attributed_to_them(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
    real_session_service: InMemorySessionService,
) -> None:
    """An approver typing in the chat acts with their own authority, not the initiator's."""
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    registry.get.return_value = ScriptedAgent()
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)  # kickoff

    queued = await client.post(
        f"{_base(execution)}/input",
        json={"message": "hi from alice"},
        headers={"X-User-Id": "alice"},
    )
    assert assert_ok(queued, status=202)["status"] == "queued"

    agent = AppendingAgent(
        real_session_service, execution, [_user_event("hi from alice")]
    )
    registry.get.return_value = agent
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    (sent,) = agent.inputs
    assert sent.state["temp:actingUserId"] == "alice"
    history = assert_ok(await client.get(f"{_base(execution)}/messages"))
    alice = [m for m in history["messages"] if m.get("content") == "hi from alice"]
    assert alice[0]["senderUserId"] == "alice"


async def test_a_form_answer_resumes_its_call_and_skips_the_no_op_acks(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
    real_session_service: InMemorySessionService,
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    form = [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id="tc-1",
            tool_call_name="render_a2ui",
        ),
        ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id="tc-1"),
        ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id="tc-2",
            tool_call_name="render_a2ui",
        ),
        ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id="tc-2"),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]
    registry.get.return_value = ScriptedAgent(form)
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)
    paused = await _session(engine, execution["sessionId"])
    assert paused.status is ExecutionSessionStatus.waiting_for_input

    assert_ok(
        await client.post(
            f"{_base(execution)}/input",
            json={"a2uiAction": {"toolCallId": "tc-1", "content": "submitted"}},
            headers={"X-User-Id": execution["initiatorId"]},
        ),
        status=202,
    )
    agent = AppendingAgent(
        real_session_service,
        execution,
        [
            _tool_response_event("tc-2", {"status": "rendered"}),
            _tool_response_event("tc-1", {"result": "submitted"}),
        ],
    )
    registry.get.return_value = agent
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    results = {
        m.tool_call_id: m.content
        for m in agent.inputs[0].messages
        if isinstance(m, ToolMessage)
    }
    assert results == {
        "tc-1": "submitted",
        "tc-2": json.dumps({"status": "rendered"}),
    }
    history = assert_ok(await client.get(f"{_base(execution)}/messages"))["messages"]
    senders = {
        m["toolCallId"]: m["senderUserId"] for m in history if m["role"] == "tool"
    }
    # The answer is the initiator's; the no-op acknowledgement is nobody's.
    assert senders == {"tc-1": execution["initiatorId"], "tc-2": None}


async def test_work_after_a_task_starts_is_associated_with_it(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
    real_session_service: InMemorySessionService,
) -> None:
    from google.adk.events.event import Event
    from google.genai import types

    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    (task,) = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )
    started = Event(
        author="agent",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="update_workflow_task",
                        args={"task_id": task["id"], "status": "in_progress"},
                    )
                )
            ],
        ),
    )
    work = Event(
        author="agent",
        content=types.Content(role="model", parts=[types.Part(text="work done")]),
    )
    registry.get.return_value = AppendingAgent(
        real_session_service, execution, [_user_event("kick off"), started, work]
    )
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    messages = assert_ok(await client.get(f"{_base(execution)}/messages"))["messages"]
    assert messages[0]["workflowTaskId"] is None
    assert messages[-1]["workflowTaskId"] == task["id"]


async def test_a_turn_reaches_viewers_through_the_stream(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """Joining at the history's cursor replays the turn once, ending with it."""
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    cursor = assert_ok(await client.get(f"{_base(execution)}/messages"))["streamCursor"]
    registry.get.return_value = ScriptedAgent()
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    response = await client.get(f"{_base(execution)}/stream", params={"after": cursor})

    assert response.status_code == 200
    # A compressing proxy would hold the stream back until it closes, and a turn
    # waiting on a person's answer never closes on its own.
    assert "no-transform" in response.headers["cache-control"]
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["RUN_STARTED", "RUN_FINISHED"]
    after = assert_ok(await client.get(f"{_base(execution)}/messages"))["streamCursor"]
    assert after > cursor


async def test_a_viewer_from_the_last_turn_still_gets_the_next_one(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """Stream ids never go backwards, though each turn drops the previous turn's rows.

    A viewer that read the history after one turn waits for events after that
    turn's last id. Had the next turn's ids restarted below it -- SQLite reuses
    the ids of deleted rows unless told not to -- the viewer would never see it.
    """
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    registry.get.return_value = ScriptedAgent()
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)  # kickoff
    cursor = assert_ok(await client.get(f"{_base(execution)}/messages"))["streamCursor"]

    assert_ok(
        await client.post(f"{_base(execution)}/input", json={"message": "next"}),
        status=202,
    )
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)
    response = await client.get(f"{_base(execution)}/stream", params={"after": cursor})

    types = [
        json.loads(line.removeprefix("data: "))["type"]
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert types == ["RUN_STARTED", "RUN_FINISHED"]


async def test_the_history_stops_where_a_running_turn_began(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
    real_session_service: InMemorySessionService,
) -> None:
    """A viewer joining mid-turn gets the turn from the stream, not twice."""
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    registry.get.return_value = AppendingAgent(
        real_session_service, execution, [_user_event("before")]
    )
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)
    async with AsyncSession(engine) as db:
        row = await db.get(ExecutionSession, execution["sessionId"])
        assert row is not None
        # A turn is under way that began after the one event above.
        row.active_run_id = "run-now"
        row.run_event_index = 1
        db.add(row)
        await db.commit()
    await AppendingAgent(
        real_session_service, execution, [_user_event("during")]
    ).persist()

    history = assert_ok(await client.get(f"{_base(execution)}/messages"))
    assert [m.get("content") for m in history["messages"]] == ["before"]


async def test_the_history_shows_a_queued_turn_and_its_message_once(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
    real_session_service: InMemorySessionService,
) -> None:
    """A viewer sees the kickoff and that the agent is busy before the turn runs."""
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)

    queued = assert_ok(await client.get(f"{_base(execution)}/messages"))
    assert queued["running"] is True
    assert [(m["role"], m["content"]) for m in queued["messages"]] == [
        ("user", EXECUTION_KICKOFF_PROMPT)
    ]
    assert queued["messages"][0]["senderUserId"] == execution["initiatorId"]

    registry.get.return_value = AppendingAgent(
        real_session_service, execution, [_user_event(EXECUTION_KICKOFF_PROMPT)]
    )
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    done = assert_ok(await client.get(f"{_base(execution)}/messages"))
    assert done["running"] is False
    assert [m.get("content") for m in done["messages"]] == [EXECUTION_KICKOFF_PROMPT]


async def test_input_is_refused_while_the_session_is_busy_or_awaiting_approval(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)  # its kickoff is still queued
    busy = await client.post(f"{_base(execution)}/input", json={"message": "hi"})
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "SESSION_RUN_IN_PROGRESS"

    approval_id = await _insert_approval(engine, execution["id"])
    registry.get.return_value = ScriptedAgent(_asks_for_approval(approval_id))
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)
    waiting = await client.post(f"{_base(execution)}/input", json={"message": "hi"})
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "SESSION_AWAITING_APPROVAL"


async def test_only_the_initiator_answers_a_form_and_only_an_open_one(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    registry.get.return_value = ScriptedAgent()
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)  # kickoff
    answer = {"a2uiAction": {"toolCallId": "tc-9", "content": "x"}}

    not_open = await client.post(
        f"{_base(execution)}/input",
        json=answer,
        headers={"X-User-Id": execution["initiatorId"]},
    )
    assert not_open.status_code == 422
    assert not_open.json()["error"]["code"] == "INVALID_SESSION_INPUT"
    someone_else = await client.post(
        f"{_base(execution)}/input", json=answer, headers={"X-User-Id": "alice"}
    )
    assert someone_else.status_code == 403


async def test_a_turn_is_told_which_files_the_session_holds(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """The file listing reaches the agent from the server's records, as context."""
    client, _engine, runner, registry = runner_env
    execution = await _execute(client)
    assert_ok(
        await client.post(
            f"/api/v1/workflow-executions/{execution['id']}/files",
            files={"file": ("input.csv", b"a,b\n1,2\n", "text/csv")},
        ),
        status=201,
    )
    agent = ScriptedAgent()
    registry.get.return_value = agent
    await runner.run_turn(execution["sessionId"], DEFAULT_TEST_TENANT_ID)

    entries = {c.description: c.value for c in agent.inputs[0].context}
    assert "input.csv" in entries["Files attached to this session"]


# ---------- parallel branches ----------


def _says(text: str) -> list[Any]:
    """A turn whose only output is one assistant message saying ``text``."""
    from ag_ui.core import (
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )

    return [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START, message_id="m", role="assistant"
        ),
        TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT, message_id="m", delta=text
        ),
        TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id="m"),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]


async def _execute_diamond(
    client: AsyncClient,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Run a workflow A -> (B, C) -> D; return the run and its task ids by title."""
    from tests._workflow import add_template, generate_workflow, publish_workflow

    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    a = await add_template(client, wf["id"], title="A")
    b = await add_template(client, wf["id"], title="B", depends_on_ids=[a["id"]])
    c = await add_template(client, wf["id"], title="C", depends_on_ids=[a["id"]])
    await add_template(client, wf["id"], title="D", depends_on_ids=[b["id"], c["id"]])
    await publish_workflow(client, wf["id"])
    execution: dict[str, Any] = assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    tasks = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )
    return execution, {t["title"]: t["id"] for t in tasks}


async def _work(task_id: str, session_id: str, initiator: str) -> None:
    """Have the session's agent start and complete a task, through its tool."""
    from types import SimpleNamespace

    from infrastructure.workflow_task_tools import update_workflow_task

    ctx = SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=initiator, state=None
    )
    for status in ("in_progress", "completed"):
        result = await update_workflow_task(task_id, ctx, status=status)  # type: ignore[arg-type]
        assert "error" not in result, result


async def test_a_branch_point_forks_a_session_and_the_join_returns_to_main(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """A -> (B, C) -> D: C runs in a forked branch, and D waits for it in main."""
    client, engine, runner, registry = runner_env
    execution, ids = await _execute_diamond(client)
    main, initiator = execution["sessionId"], execution["initiatorId"]
    registry.get.return_value = ScriptedAgent()
    await runner.run_turn(main, DEFAULT_TEST_TENANT_ID)  # kickoff

    await _work(ids["A"], main, initiator)

    sessions = assert_ok(
        await client.get(f"/api/v1/workflow-executions/{execution['id']}/sessions")
    )
    (branch,) = [s for s in sessions if s["parentId"] == main]
    assert branch["status"] == "queued"
    owners = {
        t["title"]: t["sessionId"]
        for t in assert_ok(
            await client.get(
                f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
            )
        )
    }
    assert owners["B"] == main
    assert owners["C"] == branch["id"]

    # Both branches finish their task; the join still waits for the branch
    # session itself to finish, so its summary exists.
    await _work(ids["B"], main, initiator)
    await _work(ids["C"], branch["id"], initiator)
    async with AsyncSession(engine) as db:
        from models.workflow_task import WorkflowTask

        join = await db.get(WorkflowTask, ids["D"])
        assert join is not None and join.session_id is None

    registry.get.return_value = ScriptedAgent(_says("C went fine: 3 rows."))
    await runner.run_turn(branch["id"], DEFAULT_TEST_TENANT_ID)

    finished = await _session(engine, branch["id"])
    assert finished.status is ExecutionSessionStatus.done
    assert finished.summary == "C went fine: 3 rows."
    async with AsyncSession(engine) as db:
        join = await db.get(WorkflowTask, ids["D"])
        assert join is not None and join.session_id == main

    # The main session's next turn is told what the branch reported, and
    # works the join -- finishing the run while the turn is still under way.
    class WorksJoin(ScriptedAgent):
        async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
            self.inputs.append(input_data)
            start, finish = _finished()
            yield start
            await _work(ids["D"], main, initiator)
            yield finish

    agent = WorksJoin()
    registry.get.return_value = agent
    await runner.run_turn(main, DEFAULT_TEST_TENANT_ID)
    (sent,) = agent.inputs
    reports = {c.description: c.value for c in sent.context}
    assert "C went fine: 3 rows." in reports["Finished branch reports"]
    assert (await _session(engine, main)).status is ExecutionSessionStatus.done


# ---------- waiting until a time ----------


class WaitingAgent(ScriptedAgent):
    """A scripted agent that calls the real ``wait_until`` tool on its first turn."""

    def __init__(self, session_id: str, user_id: str, resume_at: str) -> None:
        super().__init__()
        self.context: Any = SimpleNamespace(
            session=SimpleNamespace(id=session_id), user_id=user_id, state=None
        )
        self.resume_at = resume_at
        self.results: list[dict[str, Any]] = []

    async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
        if not self.inputs:
            self.results.append(await wait_until(self.resume_at, self.context))
        async for event in super().run(input_data):
            yield event


async def _due(engine: AsyncEngine) -> list[str]:
    async with AsyncSession(engine) as db:
        return [sid for sid, _tid in await due_sessions(db)]


async def _set_resume_at(engine: AsyncEngine, session_id: str, at: datetime) -> None:
    async with AsyncSession(engine) as db:
        row = await db.get(ExecutionSession, session_id)
        assert row is not None
        row.resume_at = at
        db.add(row)
        await db.commit()


async def _run_status(
    engine: AsyncEngine, execution_id: str
) -> WorkflowExecutionStatus:
    async with AsyncSession(engine) as db:
        row = await db.get(WorkflowExecution, execution_id)
        assert row is not None
        return row.status


async def test_waiting_until_a_time_schedules_the_session_and_resumes_it_then(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    sid = execution["sessionId"]
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    agent = WaitingAgent(sid, execution["initiatorId"], later)
    registry.get.return_value = agent

    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert "resume_at" in agent.results[0]
    assert any(c.description == "Current time" for c in agent.inputs[0].context)
    row = await _session(engine, sid)
    assert row.status is ExecutionSessionStatus.scheduled
    assert row.resume_at is not None
    assert sid not in await _due(engine)
    assert (
        await _run_status(engine, execution["id"]) is WorkflowExecutionStatus.scheduled
    )

    await _set_resume_at(engine, sid, datetime.now(UTC) - timedelta(seconds=1))
    assert sid in await _due(engine)
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    (wake,) = [m for m in agent.inputs[1].messages if isinstance(m, UserMessage)]
    assert "wait_until" in str(wake.content)
    row = await _session(engine, sid)
    assert row.status is ExecutionSessionStatus.idle
    assert row.resume_at is None
    assert await _run_status(engine, execution["id"]) is WorkflowExecutionStatus.running


async def test_a_message_wakes_a_scheduled_session_early(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    sid = execution["sessionId"]
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    registry.get.return_value = WaitingAgent(sid, execution["initiatorId"], later)
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert_ok(
        await client.post(f"{_base(execution)}/input", json={"message": "go now"}),
        status=202,
    )

    row = await _session(engine, sid)
    assert row.status is ExecutionSessionStatus.queued
    assert row.resume_at is None
    assert await _run_status(engine, execution["id"]) is WorkflowExecutionStatus.running


async def test_a_finished_run_keeps_its_status_when_a_session_is_scheduled(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    sid = execution["sessionId"]
    registry.get.return_value = WaitingAgent(sid, execution["initiatorId"], "")
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)
    async with AsyncSession(engine) as db:
        run = await db.get(WorkflowExecution, execution["id"])
        assert run is not None
        run.status = WorkflowExecutionStatus.completed
        run.finished_at = datetime.now(UTC)
        db.add(run)
        await db.commit()
        await SqlExecutionSessionRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).set_state(
            sid,
            status=ExecutionSessionStatus.scheduled,
            user_id=execution["initiatorId"],
        )

    assert (
        await _run_status(engine, execution["id"]) is WorkflowExecutionStatus.completed
    )


async def test_wait_until_refuses_a_time_that_has_passed(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    sid = execution["sessionId"]
    earlier = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    agent = WaitingAgent(sid, execution["initiatorId"], earlier)
    registry.get.return_value = agent

    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert "error" in agent.results[0]
    assert (await _session(engine, sid)).status is ExecutionSessionStatus.idle


async def test_wait_until_reads_a_time_without_an_offset_in_the_local_zone(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution = await _execute(client)
    sid = execution["sessionId"]
    zone = ZoneInfo(get_settings().timezone)
    local = (datetime.now(zone) + timedelta(days=1)).replace(microsecond=0)
    agent = WaitingAgent(
        sid, execution["initiatorId"], local.replace(tzinfo=None).isoformat()
    )
    registry.get.return_value = agent

    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert agent.results[0]["resume_at"] == local.astimezone(UTC).isoformat()


class StartingAgent(ScriptedAgent):
    """A scripted agent that tries to start one task on every turn, for real."""

    def __init__(self, session_id: str, user_id: str, task_id: str) -> None:
        super().__init__()
        self.context: Any = SimpleNamespace(
            session=SimpleNamespace(id=session_id), user_id=user_id, state=None
        )
        self.task_id = task_id
        self.results: list[dict[str, Any]] = []

    async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
        self.results.append(
            await update_workflow_task(self.task_id, self.context, status="in_progress")
        )
        async for event in super().run(input_data):
            yield event


async def _execute_with_an_asking_tool(
    client: AsyncClient, engine: AsyncEngine
) -> tuple[dict[str, Any], str]:
    """Execute a workflow whose one task binds a tool marked ``elicits``."""
    async with AsyncSession(engine) as db:
        server = MCPServer(
            name="vault",
            transport=McpTransport.streamable_http,
            url="https://example.com/mcp",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        server_id = server.id
        db.add(server)
        await db.commit()
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    await add_template(
        client,
        wf["id"],
        tool_bindings=[{"mcpServerId": server_id, "toolName": "set", "elicits": True}],
    )
    await publish_workflow(client, wf["id"])
    execution: dict[str, Any] = assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    (task,) = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )
    return execution, task["id"]


async def test_a_task_whose_tool_asks_waits_for_its_initiator_to_resume_it(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    client, engine, runner, registry = runner_env
    execution, task_id = await _execute_with_an_asking_tool(client, engine)
    sid = execution["sessionId"]
    agent = StartingAgent(sid, execution["initiatorId"], task_id)
    registry.get.return_value = agent

    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)  # the kickoff

    assert agent.results[0]["waiting_for_initiator"] == task_id
    row = await _session(engine, sid)
    assert row.status is ExecutionSessionStatus.waiting_for_initiator
    assert row.initiator_task_id == task_id
    async with AsyncSession(engine) as db:
        notes = (await db.exec(select(Notification))).all()
    assert [(n.user_id, n.type) for n in notes] == [
        (execution["initiatorId"], NotificationType.elicitation_request)
    ]
    assert await _run_status(engine, execution["id"]) is WorkflowExecutionStatus.running

    # The resume button: a message from the initiator.
    assert_ok(
        await client.post(f"{_base(execution)}/input", json={"message": "resume"}),
        status=202,
    )
    assert (await _session(engine, sid)).initiator_task_id is None
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert agent.results[1]["status"] == "in_progress"
    assert (await _session(engine, sid)).status is ExecutionSessionStatus.idle


async def test_only_the_initiator_resumes_a_task_whose_tool_asks(
    runner_env: tuple[AsyncClient, AsyncEngine, SessionRunner, MagicMock],
) -> None:
    """Someone else typing is not the initiator being there to answer."""
    client, engine, runner, registry = runner_env
    execution, task_id = await _execute_with_an_asking_tool(client, engine)
    sid = execution["sessionId"]
    agent = StartingAgent(sid, execution["initiatorId"], task_id)
    registry.get.return_value = agent
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert_ok(
        await client.post(
            f"{_base(execution)}/input",
            json={"message": "go"},
            headers={"X-User-Id": "alice"},
        ),
        status=202,
    )
    await runner.run_turn(sid, DEFAULT_TEST_TENANT_ID)

    assert "waiting_for_initiator" in agent.results[1]
    assert (await _session(engine, sid)).status is (
        ExecutionSessionStatus.waiting_for_initiator
    )
