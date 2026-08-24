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
transitions below are allowed to happen. There is a read view,
:class:`OutboundEmailRead`, backing the super_admin-only List/Get/Delete API
(see :mod:`routers.outbound_emails`) — "no PATCH surface" does not mean
"no read surface".
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import EmailStr, field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z, iso_z_or_none
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


class OutboundEmailRead(BaseEntity):
    """Read view of an OutboundEmail returned by the super_admin-only queue API.

    Mirrors every persisted scalar field 1:1 -- nothing here is sensitive or
    derived, unlike ``SecretRead``/``UserRead``, so every field is safely
    filterable and sortable through :func:`repositories.query.apply_filters`/
    :func:`~repositories.query.apply_sort`.
    """

    model_config = _alias_config

    tenant_id: str
    notification_id: str | None = None
    to_email: str
    subject: str
    body: str
    status: OutboundEmailStatus
    attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    sent_at: datetime | None = None

    @field_serializer("next_attempt_at", when_used="json")
    def _serialize_next_attempt_at(self, dt: datetime) -> str:
        """Serialize as ISO-8601 with a ``Z`` suffix."""
        return iso_z(dt)

    @field_serializer("lease_expires_at", "sent_at", when_used="json")
    def _serialize_optional_datetime(self, dt: datetime | None) -> str | None:
        """Serialize as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return iso_z_or_none(dt)
