"""Per-message metadata model for the shared workflow session chat.

A workflow session chat is a single ADK session keyed by the session owner, yet
several people -- the applicant and one or more approvers -- post messages into
it, and the agent works through a list of WorkflowTasks while it runs. ADK
records every event with only an author role (``"user"`` or the agent) and no
further identity, so on its own the conversation cannot tell who sent a human
message or which task the agent was working on when it produced a message.

A ``MessageMeta`` row holds the side-channel facts about one ADK event (one chat
message): ``sender_user_id`` -- the real user who sent it -- and
``workflow_task_id`` -- the WorkflowTask in progress when it was produced. Both
fields are optional; a row carries whichever facts are known. Rows are written
after each agent run and read back when listing messages so the UI can show each
sender's avatar/name and group messages under their task. Messages without a row
(legacy history, or a null field) fall back gracefully in the UI.
"""

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from models.base import BaseEntity


class MessageMeta(BaseEntity, table=True):
    """Database-persisted side-channel metadata for one ADK chat event.

    ``workflow_session_id`` references the owning workflow session
    (``ON DELETE CASCADE``), so deleting the session removes its metadata.
    ``adk_event_id`` is the id of the ADK event, which is also the ``id`` of the
    message surfaced to the frontend. ``sender_user_id`` references the user who
    actually sent a human message (``ON DELETE RESTRICT``, matching the audit
    user FKs) and is null for agent-authored events. ``workflow_task_id``
    references the WorkflowTask that was in progress when the event was produced
    (``ON DELETE CASCADE``) and is null for messages produced outside any task
    (for example the initial planning exchange). ``(workflow_session_id,
    adk_event_id)`` is unique so each event has at most one metadata row and
    re-recording is idempotent.
    """

    __tablename__ = "message_meta"
    __table_args__ = (
        UniqueConstraint(
            "workflow_session_id",
            "adk_event_id",
            name="uq_message_meta_ws_event",
        ),
        Index("ix_message_meta_workflow_session_id", "workflow_session_id"),
        Index("ix_message_meta_sender_user_id", "sender_user_id"),
        Index("ix_message_meta_workflow_task_id", "workflow_task_id"),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
            name="fk_message_meta_workflow_session_id",
        ),
        ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_message_meta_sender_user_id",
        ),
        ForeignKeyConstraint(
            ["workflow_task_id"],
            ["workflow_tasks.id"],
            ondelete="CASCADE",
            name="fk_message_meta_workflow_task_id",
        ),
    )

    workflow_session_id: str
    adk_event_id: str
    sender_user_id: str | None = None
    workflow_task_id: str | None = None
