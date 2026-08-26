"""Tenant-scoped writes and reporting reads for the outgoing-email queue.

This is the *producer* half of the queue. It stages a delivery request in the
caller's own transaction and answers the backlog questions the Prometheus
endpoint asks, both scoped to one tenant like every other repository here.

The *consumer* half — claiming, sending, retrying — is deliberately not here.
The queue is drained platform-wide through a single relay, so it cannot be
scoped to a tenant at all; see :mod:`repositories.outbound_email_queue`.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailRead,
    OutboundEmailStatus,
)
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class OutboundEmailRepository(Protocol):
    """Interface for enqueuing outgoing email, reporting on the backlog, and the super_admin read/delete API."""

    def stage(self, data: OutboundEmailCreate, *, user_id: str) -> OutboundEmail: ...

    async def counts_by_status(self) -> dict[OutboundEmailStatus, int]: ...

    async def oldest_pending_age_seconds(self, *, now: datetime) -> float | None: ...

    async def get(self, email_id: str) -> OutboundEmailRead | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[OutboundEmailRead]: ...

    async def delete(self, email_id: str) -> None: ...


class SqlOutboundEmailRepository:
    """SQLModel-backed implementation of OutboundEmailRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only a write method should call this -- see
        ``repositories.agent_skill.SqlAgentSkillRepository._require_tenant``.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} mutation requires a concrete tenant_id"
            )
        return self._tenant_id

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
                "tenant_id": self._require_tenant(),
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

    async def _get_scoped(self, email_id: str) -> OutboundEmail | None:
        """Return the row when it belongs to this repository's tenant, else None.

        ``tenant_id=None`` means "all tenants" (see ``get_current_tenant_scope``
        in ``dependencies/auth.py``), so the tenant filter is dropped entirely
        rather than compared against ``None`` -- ``Column == None`` compiles to
        ``IS NULL`` in SQL and would match nothing, since ``tenant_id`` is
        non-nullable.
        """
        stmt = select(OutboundEmail).where(OutboundEmail.id == email_id)
        if self._tenant_id is not None:
            stmt = stmt.where(OutboundEmail.tenant_id == self._tenant_id)
        return (await self._db.exec(stmt)).first()

    async def get(self, email_id: str) -> OutboundEmailRead | None:
        """Return the OutboundEmail with the given ID, resolved into a read model, or None."""
        email = await self._get_scoped(email_id)
        if email is None:
            return None
        return OutboundEmailRead.model_validate(email)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[OutboundEmailRead]:
        """Return a page of this tenant's queue rows, defaulting to createdAt descending.

        ``tenant_id=None`` means "all tenants" -- see the note on ``_get_scoped``.
        """
        stmt = select(OutboundEmail)
        if self._tenant_id is not None:
            stmt = stmt.where(OutboundEmail.tenant_id == self._tenant_id)
        stmt = apply_filters(stmt, OutboundEmail, filters, readable=OutboundEmailRead)
        stmt = apply_sort(
            stmt,
            OutboundEmail,
            sort,
            default=[col(OutboundEmail.created_at).desc()],
            readable=OutboundEmailRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return [OutboundEmailRead.model_validate(row) for row in result.all()]

    async def delete(self, email_id: str) -> None:
        """Delete an OutboundEmail row unconditionally.

        The terminal-status precondition (only ``sent``/``failed`` rows may be
        deleted) is enforced by :class:`services.outbound_email.OutboundEmailService`,
        not here -- this method only does the tenant-scoped existence check and
        deletion, matching every other repository's ``delete``.

        Raises:
            NotFoundError: If no row with that id exists in this tenant.
        """
        email = await self._get_scoped(email_id)
        if email is None:
            raise NotFoundError("OutboundEmail", email_id)
        await self._db.delete(email)
        await self._db.commit()


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
