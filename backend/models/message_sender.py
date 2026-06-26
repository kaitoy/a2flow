"""Message sender attribution model.

A workflow session chat is a single ADK session keyed by the session owner
(the applicant), yet several people -- the applicant and one or more approvers --
post messages into it. ADK records every human message with the author ``"user"``
and no per-person identity, so on its own the conversation cannot tell who sent
which message.

A ``MessageSender`` row records, for one ADK user event, the real user who sent
it. Rows are written after each agent run by diffing the session's user events,
and read back when listing messages so the UI can show each sender's avatar and
name. Messages without a row (legacy history sent before this attribution
existed) fall back to the session owner in the UI.
"""

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from models.base import BaseEntity


class MessageSender(BaseEntity, table=True):
    """Database-persisted attribution of one ADK user event to its sender.

    ``workflow_session_id`` references the owning workflow session
    (``ON DELETE CASCADE``), so deleting the session removes its attributions.
    ``adk_event_id`` is the id of the ADK ``"user"`` event, which is also the
    ``id`` of the message surfaced to the frontend. ``sender_user_id`` references
    the user who actually sent the message (``ON DELETE RESTRICT``, matching the
    audit user FKs). ``(workflow_session_id, adk_event_id)`` is unique so each
    event is attributed at most once and re-recording is idempotent.
    """

    __tablename__ = "message_senders"
    __table_args__ = (
        UniqueConstraint(
            "workflow_session_id",
            "adk_event_id",
            name="uq_message_senders_ws_event",
        ),
        Index("ix_message_senders_workflow_session_id", "workflow_session_id"),
        Index("ix_message_senders_sender_user_id", "sender_user_id"),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
            name="fk_message_senders_workflow_session_id",
        ),
        ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_message_senders_sender_user_id",
        ),
    )

    workflow_session_id: str
    adk_event_id: str
    sender_user_id: str
