"""The server-side resume against the real ag-ui-adk, across a restart.

Everything else about the session runner is tested with a stand-in agent. This
pins the one assumption those tests cannot: that the messages
:func:`services.session_inputs.build_messages` builds from what
:func:`services.session_inputs.waiting_on_from_events` read off a turn really
do resume a paused ``render_approval`` call in ag-ui-adk -- including from a
brand-new ``ADKAgent`` over a brand-new session store, the way a turn resumes
on another replica or after the process restarted.

The model is a scripted ``BaseLlm``: it calls ``render_approval`` until it
sees that call's response, then answers with the response it got.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from ag_ui.core import EventType, RunAgentInput, UserMessage
from ag_ui_adk import ADKAgent
from ag_ui_adk.agui_toolset import AGUIToolset
from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.genai import types

from infrastructure.client_tools import client_tools
from services.session_inputs import SessionInput, build_messages, waiting_on_from_events


class _ApprovalAskingLlm(BaseLlm):
    """Calls ``render_approval`` until its response arrives, then echoes it."""

    model: str = "scripted"

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        responses = [
            part.function_response.response
            for content in llm_request.contents
            for part in content.parts or []
            if part.function_response is not None
            and part.function_response.name == "render_approval"
        ]
        if responses:
            part = types.Part(text=f"RESUMED {responses[-1]}")
        else:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="render_approval", args={"approvalId": "ap-1"}
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def _agent(db_file: Path) -> ADKAgent:
    """Build an ADKAgent the way ``AgentRegistry`` does, over a fresh session store."""
    app = App(
        name="resume",
        root_agent=LlmAgent(
            name="resume_agent",
            model=_ApprovalAskingLlm(),
            instruction="Ask for approval.",
            tools=[AGUIToolset()],
        ),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
    return ADKAgent.from_app(
        app,
        user_id_extractor=lambda _input: "owner",
        session_service=SqliteSessionService(str(db_file)),
        use_thread_id_as_session_id=True,
        emit_messages_snapshot=True,
        session_timeout_seconds=None,
    )


async def _run(agent: ADKAgent, messages: list[Any], run_id: str) -> list[Any]:
    events = []
    async for event in agent.run(
        RunAgentInput(
            thread_id="thread-1",
            run_id=run_id,
            state={},
            messages=messages,
            tools=client_tools(),
            context=[],
            forwarded_props={},
        )
    ):
        events.append(event)
    return events


async def test_a_paused_approval_resumes_from_a_fresh_agent(tmp_path: Path) -> None:
    db_file = tmp_path / "sessions.db"
    first = await _run(
        _agent(db_file), [UserMessage(id="u1", role="user", content="go")], "r1"
    )
    (waiting,) = waiting_on_from_events(first)
    assert waiting.name == "render_approval"
    assert waiting.approval_id == "ap-1"

    # A new agent and session store: nothing survives in memory, as after a
    # restart or on another replica.
    decision = SessionInput(
        kind="tool_result", tool_call_id=waiting.tool_call_id, content="approved"
    )
    second = await _run(_agent(db_file), build_messages([waiting], decision), "r2")

    assert not [e for e in second if e.type == EventType.RUN_ERROR]
    text = "".join(e.delta for e in second if e.type == EventType.TEXT_MESSAGE_CONTENT)
    assert text.startswith("RESUMED")
    assert "approved" in text
    assert waiting_on_from_events(second) == []
