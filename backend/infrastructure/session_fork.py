"""Forking an ADK session: a branch session starts from a copy of its parent's context.

When a run's task graph branches, the branch is worked in a new ADK session
(:mod:`services.execution_branching`). So that its agent knows what was done
and said so far -- the skill it loaded, the configuration gathered, the
decisions taken -- the new session starts with a copy of the parent's events.

Two things keep the copy from carrying the parent's *in-flight* state with it:

* Only a :func:`balanced_prefix` is copied: the parent is usually still mid-turn
  when it forks (its own task write is what forked it), and a function call
  without its response would be an unanswered call in the child's first model
  request, which the provider rejects.
* ag-ui-adk's bookkeeping in the session state is not copied: the thread id it
  finds a session by, the client-tool calls it is waiting on, and the id remaps
  of those calls all belong to the parent. Copied events get fresh ids and no
  ``state_delta``, so replaying them cannot write that state back either.
"""

from collections.abc import Sequence
from typing import Any

from google.adk.events import Event
from google.adk.sessions import BaseSessionService

#: ag-ui-adk's per-session bookkeeping keys, which describe the parent's own
#: run and must not leak into a fork.
_AG_UI_STATE_KEYS = frozenset(
    {
        "_ag_ui_thread_id",
        "pending_tool_calls",
        "lro_tool_call_id_remap",
        "_ag_ui_invocation_id",
    }
)

#: The state key ag-ui-adk finds a session by when it is given a thread id.
_THREAD_ID_KEY = "_ag_ui_thread_id"


def balanced_prefix(events: Sequence[Event]) -> list[Event]:
    """Return the longest leading run of events in which every function call is answered.

    Args:
        events: A session's events, in order.

    Returns:
        The events up to the last point where no function call was still
        waiting for its response.
    """
    open_calls: set[str] = set()
    cut = 0
    for index, event in enumerate(events):
        for call in event.get_function_calls():
            if call.id:
                open_calls.add(call.id)
        for response in event.get_function_responses():
            open_calls.discard(response.id or "")
        if not open_calls:
            cut = index + 1
    return list(events[:cut])


def fork_state(parent_state: dict[str, Any], child_id: str) -> dict[str, Any]:
    """Return the state a fork starts with: the parent's, minus ag-ui-adk's bookkeeping.

    Args:
        parent_state: The parent session's state.
        child_id: The new session's id, which is also its AG-UI thread id.

    Returns:
        The child's initial state.
    """
    state = {k: v for k, v in parent_state.items() if k not in _AG_UI_STATE_KEYS}
    state[_THREAD_ID_KEY] = child_id
    return state


async def fork_adk_session(
    service: BaseSessionService,
    *,
    app_name: str,
    user_id: str,
    parent_id: str,
    child_id: str,
) -> int:
    """Create ``child_id`` as a copy of ``parent_id``'s settled context.

    Args:
        service: The ADK session store.
        app_name: The tenant-scoped ADK app name both sessions live under.
        user_id: The user both sessions are keyed by (the run's initiator).
        parent_id: The session to copy.
        child_id: The new session's id.

    Returns:
        How many events were copied; the child's own events start after them.
    """
    parent = await service.get_session(
        app_name=app_name, user_id=user_id, session_id=parent_id
    )
    events = balanced_prefix(parent.events) if parent else []
    child = await service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=child_id,
        state=fork_state(dict(parent.state) if parent else {}, child_id),
    )
    for event in events:
        await service.append_event(
            child,
            event.model_copy(
                update={
                    "id": Event.new_id(),
                    "actions": event.actions.model_copy(update={"state_delta": {}}),
                }
            ),
        )
    return len(events)
