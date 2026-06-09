"""Notification data models for create, update, read, and database persistence.

A Notification is a per-user message surfaced in the GUI's notification center
(the toolbar bell). Notifications are generated as a side effect of workflow
activity — for example when the agent registers a plan and waits for human
approval (``approval_request``) or when every task in a workflow session reaches
a terminal state (``session_completed``).

The ``user_id`` column is the **recipient** of the notification and is distinct
from the inherited ``created_by`` / ``updated_by`` audit fields (which record the
actor that produced the record). ``workflow_session_id`` links the notification
to the workflow session it concerns so the UI can deep-link to it.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class NotificationType(StrEnum):
    """Kinds of events that produce a notification."""

    approval_request = "approval_request"
    session_completed = "session_completed"


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
    and the optional ``body`` / ``workflow_session_id`` link, and defaults
    ``read`` to ``False`` so new notifications start unread.
    """

    user_id: str
    type: NotificationType
    title: str
    body: str | None = None
    workflow_session_id: str | None = None
    read: bool = False


class Notification(NotificationCreate, BaseEntity, table=True):
    """Database-persisted Notification addressed to a single recipient user.

    ``user_id`` references the recipient (``ON DELETE CASCADE``); the optional
    ``workflow_session_id`` references the workflow session the notification is
    about (``ON DELETE CASCADE``), so deleting either removes the notification.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_workflow_session_id", "workflow_session_id"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_notifications_user_id",
        ),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
            name="fk_notifications_workflow_session_id",
        ),
    )
