"""Tenant-scoped writes and reporting reads for the outgoing-email queue.

This is the *producer* half of the queue. It stages a delivery request in the
caller's own transaction and answers the backlog questions the Prometheus
endpoint asks, both scoped to one tenant like every other repository here.

The *consumer* half — claiming, sending, retrying — is deliberately not here.
The queue is drained platform-wide through a single relay, so it cannot be
scoped to a tenant at all; see :mod:`repositories.outbound_email_queue`.
"""

from datetime import datetime
from typing import Protocol

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailStatus,
)


class OutboundEmailRepository(Protocol):
    """Interface for enqueuing outgoing email and reporting on the backlog."""

    def stage(self, data: OutboundEmailCreate, *, user_id: str) -> OutboundEmail: ...

    async def counts_by_status(self) -> dict[OutboundEmailStatus, int]: ...

    async def oldest_pending_age_seconds(self, *, now: datetime) -> float | None: ...


class SqlOutboundEmailRepository:
    """SQLModel-backed implementation of OutboundEmailRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    def stage(self, data: OutboundEmailCreate, *, user_id: str) -> OutboundEmail:
        """Add a delivery request to the session **without committing** it.

        There is no committing sibling on purpose. A queued email only makes
        sense alongside the record that caused it, so the caller's transaction
        is what decides whether both exist — see
        :meth:`repositories.notification.SqlNotificationRepository.stage`.

        Args:
            data: The fully rendered message to deliver.
            user_id: The acting user recorded in the audit fields.

        Returns:
            The pending instance, already populated with its id and its
            ``pending`` scheduling defaults.
        """
        email = OutboundEmail.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(email)
        return email

    async def counts_by_status(self) -> dict[OutboundEmailStatus, int]:
        """Return how many queued messages this tenant has in each status.

        Returns:
            A count per status. Statuses with no rows are present with a count
            of zero, so a gauge series does not disappear from the exposition
            when a queue drains — a vanished series and a zero mean very
            different things to an alerting rule.
        """
        stmt = (
            select(OutboundEmail.status, func.count())
            .where(OutboundEmail.tenant_id == self._tenant_id)
            .group_by(col(OutboundEmail.status))
        )
        result = await self._db.exec(stmt)
        counted = {status: count for status, count in result.all()}
        return {status: counted.get(status, 0) for status in OutboundEmailStatus}

    async def oldest_pending_age_seconds(self, *, now: datetime) -> float | None:
        """Return the age of this tenant's longest-waiting undelivered message.

        Counts both ``pending`` and ``sending`` rows: a message stuck mid-send
        is exactly as undelivered as one still waiting, and excluding it would
        make the backlog look healthy while a relay hangs.

        Args:
            now: The reference time the age is measured back from.

        Returns:
            The age in seconds, or ``None`` when nothing is waiting.
        """
        stmt = (
            select(OutboundEmail.created_at)
            .where(
                OutboundEmail.tenant_id == self._tenant_id,
                col(OutboundEmail.status).in_(
                    [OutboundEmailStatus.pending, OutboundEmailStatus.sending]
                ),
            )
            .order_by(col(OutboundEmail.created_at).asc())
            .limit(1)
        )
        result = await self._db.exec(stmt)
        oldest = result.first()
        if oldest is None:
            return None
        return max((now - _as_aware(oldest, now)).total_seconds(), 0.0)


def _as_aware(value: datetime, reference: datetime) -> datetime:
    """Give a datetime read back from SQLite the reference value's timezone.

    PostgreSQL stores these columns as ``timestamptz`` and hands back aware
    values; SQLite has no such type and hands back naive ones. Subtracting the
    two kinds raises, so normalize before doing arithmetic.

    Args:
        value: The datetime read from the database.
        reference: A datetime whose ``tzinfo`` to adopt when ``value`` is naive.

    Returns:
        ``value``, guaranteed to have the same awareness as ``reference``.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    return value
