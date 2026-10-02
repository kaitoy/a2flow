"""Tests for forking a branch session's ADK session from its parent's."""

from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from infrastructure.session_fork import balanced_prefix, fork_adk_session, fork_state

APP = "app"
USER = "owner"


def _call(call_id: str) -> Event:
    return Event(
        author="agent",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(id=call_id, name="t", args={})
                )
            ],
        ),
    )


def _response(call_id: str) -> Event:
    return Event(
        author="tool",
        content=types.Content(
            role="function",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id, name="t", response={}
                    )
                )
            ],
        ),
    )


def _text(text: str) -> Event:
    return Event(
        author="user", content=types.Content(role="user", parts=[types.Part(text=text)])
    )


def test_the_prefix_stops_before_an_unanswered_call() -> None:
    """The parent is mid-turn when it forks; its open call must not be copied."""
    events = [_text("go"), _call("c1"), _response("c1"), _call("c2")]
    assert balanced_prefix(events) == events[:3]


def test_the_fork_drops_the_parents_ag_ui_bookkeeping() -> None:
    state = fork_state(
        {
            "skill": "loaded",
            "_ag_ui_thread_id": "parent",
            "pending_tool_calls": ["x"],
            "lro_tool_call_id_remap": {"a": "b"},
            "_ag_ui_invocation_id": "inv",
        },
        "child",
    )
    assert state == {"skill": "loaded", "_ag_ui_thread_id": "child"}


async def test_a_fork_copies_the_settled_history_under_new_ids() -> None:
    service = InMemorySessionService()  # type: ignore[no-untyped-call]
    parent = await service.create_session(
        app_name=APP,
        user_id=USER,
        session_id="parent",
        state={"_ag_ui_thread_id": "parent"},
    )
    for event in [_text("go"), _call("c1"), _response("c1"), _call("c2")]:
        await service.append_event(parent, event)
    parent_ids = {e.id for e in parent.events}

    copied = await fork_adk_session(
        service, app_name=APP, user_id=USER, parent_id="parent", child_id="child"
    )

    child = await service.get_session(app_name=APP, user_id=USER, session_id="child")
    assert child is not None
    assert copied == 3
    assert [e.content for e in child.events] == [e.content for e in parent.events[:3]]
    assert not parent_ids & {e.id for e in child.events}
    assert child.state["_ag_ui_thread_id"] == "child"
    # The parent is untouched: ag-ui-adk still finds it by its own thread id.
    reread = await service.get_session(app_name=APP, user_id=USER, session_id="parent")
    assert reread is not None
    assert reread.state["_ag_ui_thread_id"] == "parent"
    assert len(reread.events) == 4
