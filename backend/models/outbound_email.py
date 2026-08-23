"""Queue row for one outgoing notification email.

A row here is a *request to deliver one message*, written in the same
transaction as the :class:`~models.notification.Notification` it belongs to (see
:class:`services.notification_dispatch.NotificationDispatcher`) and drained
later by :class:`services.email_queue_worker.EmailQueueWorker`. Splitting the
write from the send is what makes delivery survivable: a relay that is down when
the notification is produced no longer loses the message, it only delays it.

**The message is rendered at enqueue time**, not at send time. ``to_email``,
``subject`` and ``body`` are frozen here from facts that were true when the
notification was produced — who the recipient was, whether their address was
verified, what the deployment's base URL was. The worker therefore needs to know
nothing about tenants, users, or notification kinds; it just sends what the row
says.

There is no ``OutboundEmailUpdate``: the table has no PATCH surface. Every
mutation after insert is a named lifecycle step on
:class:`repositories.outbound_email_queue.SqlOutboundEmailQueue` (claim, mark
sent, reschedule, mark failed), which is also the only place the ``status``
transitions below are allowed to happen.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import EmailStr
from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime
from models.constraints import BodyText, ShortText
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class OutboundEmailStatus(StrEnum):
    """Lifecycle of one queued message.

    ``pending`` → ``sending`` → ``sent`` is the happy path. A transient failure
    returns the row to ``pending`` with a later ``next_attempt_at``; a permanent
    failure, or exhausting the retry budget, lands it in ``failed``, where it is
    kept as a dead letter rather than deleted.
    """

    pending = "pending"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class OutboundEmailCreate(SQLModel):
    """Enqueue payload: the fully rendered message and what it belongs to.

    Everything the worker needs to send is here. The scheduling and outcome
    columns on :class:`OutboundEmail` are owned by the queue repository and are
    never supplied by the caller.
    """

    model_config = _alias_config

    notification_id: str | None = None
    to_email: EmailStr
    subject: ShortText
    body: BodyText


class OutboundEmail(OutboundEmailCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted delivery request for one notification email.

    ``notification_id`` references the notification this message announces
    (``ON DELETE CASCADE``), so deleting a notification — or the user, execution,
    or workflow it cascades from — also drops any mail still queued for it. It is
    nullable so the queue is not structurally tied to notifications.

    ``tenant_id`` comes from :class:`~models.tenant_scoped.TenantScoped` and is
    carried purely for reporting: the queue is drained platform-wide through a
    single relay (see :mod:`repositories.outbound_email_queue`), but the
    Prometheus gauges in :mod:`routers.metrics` break the backlog down per
    tenant like every other series they export.
    """

    __tablename__ = "outbound_emails"

    status: OutboundEmailStatus = Field(default=OutboundEmailStatus.pending)
    attempts: int = Field(default=0)
    next_attempt_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=TZDateTime
    )
    lease_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    last_error: str | None = Field(default=None)
    sent_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    __table_args__ = (
        # The claim query's driving index: "the oldest rows that are pending and
        # already due". Status leads because it is the more selective of the two
        # once the queue is mostly `sent` rows awaiting their retention purge.
        Index("ix_outbound_emails_status_next_attempt_at", "status", "next_attempt_at"),
        Index("ix_outbound_emails_notification_id", "notification_id"),
        ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            ondelete="CASCADE",
            name="fk_outbound_emails_notification_id",
        ),
    )
