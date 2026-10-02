"""Tests for turning a queued input into AG-UI messages, and a turn into what it left open."""

import json

from ag_ui.core import (
    AssistantMessage,
    EventType,
    RunFinishedEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
    ToolMessage,
    UserMessage,
)

from services.session_inputs import (
    RECOVERY_PROMPT,
    SessionInput,
    WaitingCall,
    answered_calls,
    build_messages,
    waiting_on_from_events,
)

APPROVAL = WaitingCall(tool_call_id="adk-1", name="render_approval", approval_id="ap-1")
FORM = WaitingCall(tool_call_id="adk-2", name="render_a2ui")


def test_a_message_becomes_a_user_message() -> None:
    messages = build_messages([], SessionInput(kind="message", text="Start"))
    assert len(messages) == 1
    assert isinstance(messages[0], UserMessage)
    assert messages[0].content == "Start"


def test_a_decision_answers_its_call_and_acknowledges_open_forms() -> None:
    """Every call of the turn is answered at once, or the provider rejects the resume."""
    decision = SessionInput(
        kind="tool_result", tool_call_id="adk-1", content="approved"
    )
    carrier, *results = build_messages([FORM, APPROVAL], decision)

    assert isinstance(carrier, AssistantMessage)
    assert [(c.id, c.function.name) for c in carrier.tool_calls or []] == [
        ("adk-2", "render_a2ui"),
        ("adk-1", "render_approval"),
    ]
    assert all(isinstance(r, ToolMessage) for r in results)
    contents = {
        r.tool_call_id: r.content for r in results if isinstance(r, ToolMessage)
    }
    assert contents == {
        "adk-2": json.dumps({"status": "rendered"}),
        "adk-1": "approved",
    }


def test_a_typed_reply_closes_the_open_form_but_not_the_approval() -> None:
    """A form the reply acknowledged is no longer waited on; nobody answered the approval."""
    reply = SessionInput(kind="message", text="Use t3.medium")
    assert answered_calls([FORM, APPROVAL], reply) == ["adk-2"]

    decision = SessionInput(kind="tool_result", tool_call_id="adk-1", content="ok")
    assert answered_calls([FORM, APPROVAL], decision) == ["adk-2", "adk-1"]


def test_recovery_sends_the_recovery_prompt() -> None:
    (message,) = build_messages([], SessionInput(kind="recovery"))
    assert isinstance(message, UserMessage)
    assert message.content == RECOVERY_PROMPT


def _call(call_id: str, name: str, args: str) -> list[object]:
    return [
        ToolCallStartEvent(
            type=EventType.TOOL_CALL_START, tool_call_id=call_id, tool_call_name=name
        ),
        ToolCallArgsEvent(
            type=EventType.TOOL_CALL_ARGS, tool_call_id=call_id, delta=args[:5]
        ),
        ToolCallArgsEvent(
            type=EventType.TOOL_CALL_ARGS, tool_call_id=call_id, delta=args[5:]
        ),
        ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=call_id),
    ]


def test_open_client_calls_are_what_the_turn_waits_on() -> None:
    events = [
        *_call("adk-9", "update_workflow_task", '{"status": "in_progress"}'),
        ToolCallResultEvent(
            type=EventType.TOOL_CALL_RESULT,
            message_id="m",
            tool_call_id="adk-9",
            content="{}",
        ),
        *_call("adk-1", "render_approval", '{"approvalId": "ap-1"}'),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    ]
    assert waiting_on_from_events(events) == [APPROVAL]  # type: ignore[arg-type]
