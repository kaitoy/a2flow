"""Per-message metadata model for the shared session chats.

Both kinds of session chat are shared by several people. A *workflow session* --
the chat a WorkflowExecution runs in -- is a single ADK session keyed by the
execution's initiator, yet the applicant and one or more approvers post messages
into it, and the agent works through a list of WorkflowTasks while it runs. A
*design session* -- the chat a Workflow's task templates are refined in -- is a
single ADK session keyed by the workflow's ``created_by``, yet every ``developer``
in the tenant may drive it. ADK records every event with only an author role
(``"user"`` or the agent) and no further identity, so on its own neither
conversation can tell who sent a human message or which task the agent was
working on when it produced a message.

A ``MessageMeta`` row holds the side-channel facts about one ADK event (one chat
message): ``sender_user_id`` -- the real user who sent it -- and
``workflow_task_id`` -- the WorkflowTask in progress when it was produced. Both
fields are optional; a row carries whichever facts are known. Rows are written
after each agent run and read back when listing messages so the UI can show each
sender's avatar/name and group messages under their task. Messages without a row
(legacy history, the unattended background design run, or a null field) fall back
gracefully in the UI.

Neither chat has a table of its own, so a row names its chat through its parent
record: ``workflow_execution_id`` for a workflow session, ``workflow_id`` for a
design session. Exactly one of the two is set -- :class:`MessageScope` is the
value object callers pass around to say which.
"""

from typing import NamedTuple, Self

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from models.base import BaseEntity
from models.tenant_scoped import TenantScoped


class MessageScope(NamedTuple):
    """Identifies the session chat a :class:`MessageMeta` row belongs to.

    Exactly one field is set, matching the ``ck_message_meta_single_parent``
    check constraint. Build one through :meth:`workflow_session` or
    :meth:`design_session` rather than by hand, so the invariant holds by
    construction.
    """

    workflow_execution_id: str | None = None
    """Identifier of the WorkflowExecution whose workflow session this is."""

    workflow_id: str | None = None
    """Identifier of the Workflow whose design session this is."""

    @classmethod
    def workflow_session(cls, execution_id: str) -> Self:
        """Return the scope of a WorkflowExecution's workflow session.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.

        Returns:
            A scope naming that execution.
        """
        return cls(workflow_execution_id=execution_id)

    @classmethod
    def design_session(cls, workflow_id: str) -> Self:
        """Return the scope of a Workflow's design session.

        Args:
            workflow_id: Identifier of the owning Workflow.

        Returns:
            A scope naming that workflow.
        """
        return cls(workflow_id=workflow_id)


class MessageMeta(TenantScoped, BaseEntity, table=True):
    """Database-persisted side-channel metadata for one ADK chat event.

    Exactly one parent column is set (``ck_message_meta_single_parent``):
    ``workflow_execution_id`` references the owning WorkflowExecution for a
    workflow session, ``workflow_id`` the owning Workflow for a design session.
    Both are ``ON DELETE CASCADE``, so deleting the parent removes its metadata.

    ``adk_event_id`` is a correlation key, not always literally the ADK event
    id: for ``"user"`` events it is the event id, which is also the ``id`` of
    the message surfaced to the frontend. For tool-response events (including
    A2UI user-action acknowledgements) it is instead the resolved
    ``tool_call_id`` -- `adk_events_to_messages` regenerates a fresh random
    ``id`` for every tool message on each read, so the event id itself cannot
    be used to correlate a row back to a surfaced message; ``tool_call_id`` is
    the only value that round-trips stably. ``sender_user_id`` references the
    user who actually sent a human message or performed the user action a tool
    response carries (``ON DELETE RESTRICT``, matching the audit user FKs) and
    is null for agent-authored events; no-op render acknowledgements (the
    frontend's automatic ``{"status": "rendered"}`` tool results) are never
    recorded, so a row's presence on a tool response means a genuine action.
    ``workflow_task_id`` references the WorkflowTask that was in progress when
    the event was produced (``ON DELETE CASCADE``) and is null for messages
    produced outside any task -- always so in a design session, which edits
    task *templates* rather than working through status-ful tasks. Each parent
    pairs uniquely with ``adk_event_id`` so each event has at most one metadata
    row and re-recording is idempotent.
    """

    __tablename__ = "message_meta"
    __table_args__ = (
        CheckConstraint(
            "(workflow_execution_id IS NULL) <> (workflow_id IS NULL)",
            name="ck_message_meta_single_parent",
        ),
        UniqueConstraint(
            "workflow_execution_id",
            "adk_event_id",
            name="uq_message_meta_execution_event",
        ),
        UniqueConstraint(
            "workflow_id",
            "adk_event_id",
            name="uq_message_meta_workflow_event",
        ),
        Index("ix_message_meta_workflow_execution_id", "workflow_execution_id"),
        Index("ix_message_meta_workflow_id", "workflow_id"),
        Index("ix_message_meta_sender_user_id", "sender_user_id"),
        Index("ix_message_meta_workflow_task_id", "workflow_task_id"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_message_meta_workflow_execution_id",
        ),
        ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            ondelete="CASCADE",
            name="fk_message_meta_workflow_id",
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

    workflow_execution_id: str | None = None
    workflow_id: str | None = None
    adk_event_id: str
    sender_user_id: str | None = None
    workflow_task_id: str | None = None
