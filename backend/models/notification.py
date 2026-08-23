"""Notification data models for create, update, read, and database persistence.

A Notification is a per-user message surfaced in the GUI's notification center
(the toolbar bell). Notifications are generated as a side effect of workflow
activity — for example when the agent registers task templates and waits for human
approval (``approval_request``) or when every task in a workflow execution reaches
a terminal state (``execution_completed``).

The ``user_id`` column is the **recipient** of the notification and is distinct
from the inherited ``created_by`` / ``updated_by`` audit fields (which record the
actor that produced the record). ``workflow_execution_id`` / ``workflow_id`` link
the notification to the workflow execution or workflow it concerns; ``link`` is
the relative in-app path resolved from those ids once, at creation time, by
:func:`build_notification_link` — the single place that decides where each
notification kind deep-links to, shared by the email dispatcher and the web UI.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import BodyText, ShortText
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class NotificationType(StrEnum):
    """Kinds of events that produce a notification."""

    approval_request = "approval_request"
    execution_completed = "execution_completed"
    workflow_draft_ready = "workflow_draft_ready"
    workflow_generation_failed = "workflow_generation_failed"


class NotificationUpdate(SQLModel):
    """Partial update payload for a Notification.

    Only the read flag is mutable after creation; the message content and its
    links are fixed once the notification is generated.
    """

    model_config = _alias_config
    read: bool | None = None


class NotificationCreate(NotificationUpdate):
    """Creation payload for a Notification.

    Adds the required recipient ``user_id``, the event ``type``, the ``title``,
    and the optional ``body`` / ``workflow_execution_id`` / ``workflow_id``
    links, and defaults ``read`` to ``False`` so new notifications start
    unread. ``workflow_execution_id`` deep-links run-scoped notifications
    (approvals, completion) while ``workflow_id`` deep-links workflow-scoped
    ones (``workflow_draft_ready``).
    """

    user_id: str
    type: NotificationType
    title: ShortText
    body: BodyText | None = None
    workflow_execution_id: str | None = None
    workflow_id: str | None = None
    read: bool = False


class Notification(NotificationCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted Notification addressed to a single recipient user.

    ``user_id`` references the recipient (``ON DELETE CASCADE``); the optional
    ``workflow_execution_id`` / ``workflow_id`` reference the workflow execution or
    workflow the notification is about (``ON DELETE CASCADE``), so deleting any
    of them removes the notification. ``link`` is computed by the repository at
    creation time (see :func:`build_notification_link`), not supplied by callers,
    so it lives here rather than on ``NotificationCreate``.
    """

    __tablename__ = "notifications"
    link: str | None = None
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_workflow_execution_id", "workflow_execution_id"),
        Index("ix_notifications_workflow_id", "workflow_id"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_notifications_user_id",
        ),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_notifications_workflow_execution_id",
        ),
        ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            ondelete="CASCADE",
            name="fk_notifications_workflow_id",
        ),
    )


#: Notification kinds that concern a single workflow execution and deep-link to
#: its session chat (see :func:`build_notification_link`).
_EXECUTION_KINDS = frozenset(
    {NotificationType.approval_request, NotificationType.execution_completed}
)
#: Notification kinds that concern a workflow (not a specific run) and deep-link
#: to the workflow's admin page.
_WORKFLOW_KINDS = frozenset(
    {NotificationType.workflow_draft_ready, NotificationType.workflow_generation_failed}
)


def build_notification_link(
    notification_type: NotificationType,
    *,
    workflow_execution_id: str | None,
    workflow_id: str | None,
) -> str | None:
    """Resolve the relative in-app path this notification deep-links to.

    Run-scoped kinds (``approval_request``, ``execution_completed``) point at the
    execution's session chat; workflow-scoped kinds (``workflow_draft_ready``,
    ``workflow_generation_failed``) point at the workflow. This is the single
    place that decides the target path; the email dispatcher and the web UI both
    read the ``link`` this produces rather than re-deriving it.

    Args:
        notification_type: The kind of event the notification represents.
        workflow_execution_id: The execution the notification concerns, if any.
        workflow_id: The workflow the notification concerns, if any.

    Returns:
        The relative path, or ``None`` when the relevant id is missing —
        callers pick their own fallback (e.g. the notification centre).
    """
    if notification_type in _EXECUTION_KINDS and workflow_execution_id:
        return f"/workflow-executions/{workflow_execution_id}/session"
    if notification_type in _WORKFLOW_KINDS and workflow_id:
        return f"/admin/workflows/{workflow_id}"
    return None
