"""Sender attribution shared by the two kinds of session chat.

Both a workflow session (the chat a WorkflowExecution runs in) and a design
session (the chat a Workflow's task templates are refined in) are one ADK
session keyed by the chat's owner, driven by several people. ADK stamps each
event with an author *role* only, so "who sent this" is reconstructed around
each agent run by a read-then-diff: snapshot the session's attributable keys
before the run (:func:`attributable_keys`), then record whatever appeared
afterwards as the current user's (:func:`record_new_senders`). Both halves must
run inside the run lock, or a concurrent run appending between them would be
misattributed.

On the read side, :func:`merge_message_meta` folds the recorded facts back onto
the messages the API returns.

The functions here are deliberately free of persistence and ADK lookup concerns:
callers pass the already-fetched ADK session (or ``None`` when it does not exist
yet) and the :class:`~models.message_meta.MessageScope` naming the chat, so the
same logic serves both services.
"""

from typing import Any

from ag_ui.core import Message
from google.adk.sessions import Session

from models.message_meta import MessageMeta, MessageScope
from repositories import MessageMetaRepository

#: Tool-response payload of the frontend's no-op ``render_a2ui``
#: acknowledgement (``RENDER_ACK_CONTENT`` in ``frontend/src/lib/a2uiAction.ts``,
#: mirroring the ``@ag-ui/a2ui-middleware`` convention). Such a response merely
#: unblocks the long-running render call for a surface nobody acted on, so it
#: must not be attributed to the user whose run happened to flush it.
_RENDER_ACK_RESPONSE = {"status": "rendered"}


def attributable_keys(session: Session | None) -> set[str]:
    """Return the correlation keys of a session's attributable events.

    Two kinds of events can be attributed to a sender: ADK ``"user"`` events
    (keyed by their own event id) and tool-response (function-response) events
    -- including A2UI user-action acknowledgements -- keyed by their function
    response id (the ``tool_call_id`` the frontend sent). Snapshotting this set
    before an agent run lets the caller attribute whatever appears afterwards to
    the user who drove the run.

    Args:
        session: The ADK session to read, or ``None`` when it does not exist yet
            (before the first run).

    Returns:
        The set of correlation keys (event ids and tool_call_ids) representing
        attributable events already present in the chat; empty for ``None``.
    """
    if session is None:
        return set()
    keys: set[str] = set()
    for event in session.events:
        if event.author == "user":
            keys.add(event.id)
        for fr in event.get_function_responses():
            if fr.id:
                keys.add(fr.id)
    return keys


async def record_new_senders(
    meta: MessageMetaRepository,
    scope: MessageScope,
    session: Session | None,
    prior_keys: set[str],
    sender_user_id: str,
) -> None:
    """Attribute a session's new events to ``sender_user_id``.

    Compares the session's current attributable keys (see
    :func:`attributable_keys`) against the snapshot taken before the run; every
    key not in ``prior_keys`` was produced by the current user, so it is
    recorded (idempotently) -- new ``"user"`` events by their event id, and new
    tool-response events (including A2UI action acknowledgements) by their
    tool_call_id. Tool responses matching :data:`_RENDER_ACK_RESPONSE` are
    skipped: they are the no-op acknowledgements the frontend flushes for every
    still-pending render call on the user's next run, not actions the user
    performed, and attributing them would paint the user's avatar onto surfaces
    they never touched. Does nothing when the ADK session does not exist.

    Args:
        meta: Repository recording the per-message metadata.
        scope: The session chat the events belong to.
        session: The ADK session that was run, or ``None`` if it does not exist.
        prior_keys: The attributable keys present before the run.
        sender_user_id: The user who sent the new messages.

    Raises:
        ForeignKeyViolationError: If ``sender_user_id`` does not match a user.
    """
    if session is None:
        return
    for event in session.events:
        if event.author == "user" and event.id not in prior_keys:
            await meta.set_sender(
                scope=scope,
                adk_event_id=event.id,
                sender_user_id=sender_user_id,
            )
        for fr in event.get_function_responses():
            if fr.response == _RENDER_ACK_RESPONSE:
                continue
            if fr.id and fr.id not in prior_keys:
                await meta.set_sender(
                    scope=scope,
                    adk_event_id=fr.id,
                    sender_user_id=sender_user_id,
                )


def merge_message_meta(
    messages: list[Message], meta: dict[str, MessageMeta]
) -> list[dict[str, Any]]:
    """Serialize chat messages, folding each one's recorded metadata back in.

    Every returned record carries ``senderUserId`` and ``workflowTaskId`` --
    ``None`` when the message has no metadata row (agent-authored messages, the
    unattended background design run, legacy history) -- so the payload shape is
    identical for both kinds of session and the frontend chat components can be
    reused unchanged.

    Args:
        messages: The messages converted from the ADK session's events.
        meta: The chat's ``adk_event_id -> MessageMeta`` map.

    Returns:
        The messages as plain JSON-serializable dicts, each with the two
        attribution fields appended.
    """
    result: list[dict[str, Any]] = []
    for message in messages:
        data = message.model_dump(mode="json", by_alias=True)
        # "user" and "assistant" messages keep the ADK event id as their own id,
        # but `adk_events_to_messages` regenerates a fresh random id for every
        # "tool" message on each call -- their only stable, round-trip-safe
        # correlation key is the tool_call_id they resolve.
        key = data.get("toolCallId") if data.get("role") == "tool" else data["id"]
        row = meta.get(key) if key is not None else None
        data["senderUserId"] = row.sender_user_id if row is not None else None
        data["workflowTaskId"] = row.workflow_task_id if row is not None else None
        result.append(data)
    return result
