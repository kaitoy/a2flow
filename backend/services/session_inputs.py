"""What a server-driven turn is given, and what it leaves waiting.

A turn the browser drives arrives as a ready-made list of AG-UI messages. A turn
the server drives (:mod:`services.session_runner`) starts from a
:class:`SessionInput` -- the one piece of input queued on the session -- and
this module turns it into the same messages the browser would have sent:

* a ``tool_result`` answers one paused client-tool call (an approval's
  decision), and is preceded by a carrier assistant message naming the call,
  which ag-ui-adk needs to name the FunctionResponse;
* every *other* paused ``render_a2ui`` call is acknowledged with the no-op
  ``{"status": "rendered"}`` result, as ``buildRenderAckMessages`` does in
  ``frontend/src/lib/a2uiAction.ts`` -- a turn resumed with a call of its own
  still unanswered is rejected by the provider.

After the turn, :func:`waiting_on_from_events` reads its event stream for the
client-tool calls it left unanswered: what the next turn has to resume.
"""

import json
import uuid
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from ag_ui.core import (
    AssistantMessage,
    BaseEvent,
    FunctionCall,
    Message,
    ToolCall,
    ToolCallArgsEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
    ToolMessage,
    UserMessage,
)
from pydantic import BaseModel

from infrastructure.client_tools import (
    CLIENT_TOOL_NAMES,
    RENDER_A2UI_TOOL_NAME,
    RENDER_APPROVAL_TOOL_NAME,
)
from services.session_attribution import RENDER_ACK_RESPONSE

#: The first message of every run, sent on its initiator's behalf when the run
#: is created. The design was approved by publishing it, so it asks for no
#: confirmation.
EXECUTION_KICKOFF_PROMPT = "Start the workflow: execute the registered tasks."

#: What the agent is told when a turn resumes a session whose last turn was
#: cut off -- its process died mid-turn -- so it re-reads its tasks rather
#: than assuming the work it was doing finished.
RECOVERY_PROMPT = (
    "The previous turn was interrupted before it finished. Call "
    "list_workflow_tasks to see where the run stands, then continue."
)


class SessionInput(BaseModel):
    """The one piece of input queued on a session for its next server-driven turn.

    Attributes:
        kind: ``message`` sends ``text`` as a user message; ``tool_result``
            answers the paused call ``tool_call_id`` with ``content``;
            ``recovery`` resumes a turn that was cut off (see
            :data:`RECOVERY_PROMPT`); ``assigned`` tells the session, in
            ``text``, about tasks the server just assigned it -- sent like a
            message, but never followed by another such note
            (:func:`services.session_settle.settle_turn`).
        text: The user message, for ``message``.
        tool_call_id: The paused call being answered, for ``tool_result``.
        content: The answer, for ``tool_result``.
        sender_id: Who the turn's new messages are attributed to in the shared
            chat, or ``None`` for input nobody typed (the recovery prompt).
        acting_user_id: Whose authority the turn's tools act with -- the
            person who typed the input. ``None`` runs the turn as the run's
            initiator: input the server produced (kickoff, recovery) and an
            approval decision, which resumes the run on the initiator's behalf.
    """

    kind: Literal["message", "tool_result", "recovery", "assigned"]
    text: str | None = None
    tool_call_id: str | None = None
    content: str | None = None
    sender_id: str | None = None
    acting_user_id: str | None = None


class WaitingCall(BaseModel):
    """A client-tool call a turn left unanswered.

    Attributes:
        tool_call_id: The id the call was streamed under -- the one a result
            must name to resume it.
        name: ``render_approval`` or ``render_a2ui``.
        approval_id: For ``render_approval``, the approval it shows.
    """

    tool_call_id: str
    name: str
    approval_id: str | None = None


def answered_calls(
    waiting_on: Sequence[WaitingCall], session_input: SessionInput
) -> list[str]:
    """Return the ids of the waited-on calls a turn on ``session_input`` closes.

    That is every ``render_a2ui`` call -- :func:`build_messages` acknowledges
    each one, so a form left unanswered by a typed reply is no longer waited
    on -- plus the call a ``tool_result`` answers.

    Args:
        waiting_on: The calls the session's last turn left unanswered.
        session_input: The input the turn runs on.

    Returns:
        The closed calls' ids.
    """
    ids = [c.tool_call_id for c in waiting_on if c.name == RENDER_A2UI_TOOL_NAME]
    if session_input.kind == "tool_result" and session_input.tool_call_id:
        ids.append(session_input.tool_call_id)
    return ids


def build_messages(
    waiting_on: Sequence[WaitingCall], session_input: SessionInput
) -> list[Message]:
    """Return the AG-UI messages a server-driven turn sends for ``session_input``.

    Args:
        waiting_on: The calls the session's last turn left unanswered.
        session_input: The input to run the turn on.

    Returns:
        A carrier naming every call being answered, one ``tool`` message per
        answer, then the user message if there is one.
    """
    answered = (
        session_input.tool_call_id if session_input.kind == "tool_result" else None
    )
    results: list[tuple[str, str, str]] = [
        (call.tool_call_id, call.name, json.dumps(RENDER_ACK_RESPONSE))
        for call in waiting_on
        if call.name == RENDER_A2UI_TOOL_NAME and call.tool_call_id != answered
    ]
    if answered is not None:
        name = next(
            (c.name for c in waiting_on if c.tool_call_id == answered),
            RENDER_APPROVAL_TOOL_NAME,
        )
        results.append((answered, name, session_input.content or ""))

    messages: list[Message] = []
    if results:
        messages.append(
            AssistantMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id=call_id,
                        type="function",
                        function=FunctionCall(name=name, arguments="{}"),
                    )
                    for call_id, name, _ in results
                ],
            )
        )
        messages.extend(
            ToolMessage(
                id=str(uuid.uuid4()),
                role="tool",
                tool_call_id=call_id,
                content=content,
            )
            for call_id, _, content in results
        )
    text = RECOVERY_PROMPT if session_input.kind == "recovery" else session_input.text
    if text:
        messages.append(UserMessage(id=str(uuid.uuid4()), role="user", content=text))
    return messages


def waiting_on_from_events(events: Iterable[BaseEvent]) -> list[WaitingCall]:
    """Return the client-tool calls a turn's event stream left unanswered.

    A client tool (``render_approval``, ``render_a2ui``) is executed by the
    browser, so a turn that calls one ends with the call open; a server tool's
    call is closed by its result within the same stream.

    Args:
        events: The AG-UI events the turn produced, in order.

    Returns:
        The open client-tool calls, in the order they were made, each with the
        approval id a ``render_approval`` call names.
    """
    names: dict[str, str] = {}
    args: dict[str, str] = {}
    for event in events:
        if isinstance(event, ToolCallStartEvent):
            if event.tool_call_name in CLIENT_TOOL_NAMES:
                names[event.tool_call_id] = event.tool_call_name
                args[event.tool_call_id] = ""
        elif isinstance(event, ToolCallArgsEvent) and event.tool_call_id in args:
            args[event.tool_call_id] += event.delta
        elif isinstance(event, ToolCallResultEvent):
            names.pop(event.tool_call_id, None)
    return [
        WaitingCall(
            tool_call_id=call_id,
            name=name,
            approval_id=_approval_id(args[call_id])
            if name == RENDER_APPROVAL_TOOL_NAME
            else None,
        )
        for call_id, name in names.items()
    ]


def _approval_id(raw_args: str) -> str | None:
    """Pull ``approvalId`` out of a ``render_approval`` call's streamed arguments."""
    try:
        parsed: Any = json.loads(raw_args)
    except ValueError:
        return None
    value = parsed.get("approvalId") if isinstance(parsed, dict) else None
    return value if isinstance(value, str) else None
