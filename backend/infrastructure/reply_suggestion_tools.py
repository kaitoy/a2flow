"""ADK agent tool for proposing the user's next reply in a workflow session.

Attached to the execution agent (see :func:`infrastructure.agent.create_agent`)
so that, just before it stops to wait for the user, the agent can name a few
replies the user is likely to give. The frontend shows them as one-click drafts
under the chat input; clicking one fills the input and the user edits or sends
it themselves.

The tool stores nothing and touches no external system. Its whole payload is
its *arguments*: ADK persists every function call in the session's events, and
the frontend reads the suggestions back from the ``suggest_replies`` call in the
last agent turn -- live from the streamed tool-call event, and on reload or on
another participant's poll from the persisted history. A dedicated store would
only duplicate what the session already holds.
"""

from typing import Any


def suggest_replies(suggestions: list[str]) -> dict[str, Any]:
    """Propose replies the user is likely to send next, shown as one-click drafts.

    Call this right before you stop to wait for the user -- when you ask a
    question, request input or a confirmation, or present a surface they must
    act on. Give two to four short replies (at most 30 characters each) phrased
    the way the user would type them, for example ``["Yes, go ahead",
    "Skip this step", "Use the default"]``. Do not call it when the run is
    finished or when you are only reporting progress and will keep working.

    Args:
        suggestions: The candidate replies, in the order to show them.

    Returns:
        ``{"status": "ok"}``. The suggestions themselves are read from this
        call's arguments, so nothing else is returned.
    """
    return {"status": "ok"}
