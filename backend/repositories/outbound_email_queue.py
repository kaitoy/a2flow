"""The consumer half of the outgoing-email queue: claim, settle, retry, purge.

**Deliberately not tenant-scoped.** Every other repository that touches a
``TenantScoped`` table filters on one tenant; this one must not, and the
justification the tenant-isolation rule asks for is this: a deployment has one
SMTP relay (``SystemSettings`` is platform-scoped, not per tenant) and therefore
one sender. Scoping the drain to a tenant would mean one poller per tenant
competing for that single relay, which is exactly the thing the rate limiter
exists to prevent. What a claim returns is handed straight to
:class:`services.email_queue_worker.EmailQueueWorker`, which sends what it says
and queries nothing else — no tenant's data reaches another tenant downstream.

Mutual exclusion is not this module's job either. Exactly one process holds the
``email-queue`` advisory lock (:func:`infrastructure.locks.email_queue_key`) and
only that process calls :meth:`SqlOutboundEmailQueue.claim_batch`, which is why
the claim below is a plain read-then-update rather than ``SELECT ... FOR UPDATE
SKIP LOCKED``. That keeps one code path working on both PostgreSQL and SQLite.
``lease_expires_at`` covers the case the lock cannot: a sender that dies
mid-batch leaves rows in ``sending``, and :meth:`reclaim_expired_leases` returns
them to the queue once the lease runs out.

A claim hands back :class:`ClaimedEmail` snapshots rather than ORM instances.
The worker settles each message with a commit before moving to the next, and a
commit expires every instance in the session — so a live object read after the
previous one was settled would trigger a lazy reload from inside the send loop.
Detached data cannot do that, and the settle methods below address rows by id.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.outbound_email import OutboundEmail, OutboundEmailStatus


@dataclass(frozen=True)
class ClaimedEmail:
    """One leased message, detached from the session that produced it.

    Attributes:
        id: Primary key, used to settle the message afterwards.
        to_email: Recipient address.
        subject: Message subject line.
        body: Plain-text message body.
        attempts: How many times delivery has already been attempted. Zero on a
            message that has never been tried; the retry backoff is computed
            from this value, before the attempt about to be made is counted.
    """

    id: str
    to_email: str
    subject: str
    body: str
    attempts: int


class SqlOutboundEmailQueue:
    """SQLModel-backed drain operations over ``outbound_emails``, all tenants."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel async session the drain runs on."""
        self._db = session

    async def reclaim_expired_leases(self, *, now: datetime) -> int:
        """Return messages abandoned mid-send to the queue.

        A row sits in ``sending`` only while a sender is working on it. If that
        process dies, nothing else would ever look at the row again, so an
        expired lease is the signal to make it claimable once more. The attempt
        that died is not counted — ``attempts`` only advances when a sender
        settles a message — so a lease that expires because the relay is slow
        does not silently burn the retry budget.

        Args:
            now: The reference time leases are judged against.

        Returns:
            The number of messages returned to ``pending``.
        """
        stmt = (
            update(OutboundEmail)
            .where(
                col(OutboundEmail.status) == OutboundEmailStatus.sending,
                col(OutboundEmail.lease_expires_at).is_not(None),
                col(OutboundEmail.lease_expires_at) < now,
            )
            .values(status=OutboundEmailStatus.pending, lease_expires_at=None)
            .execution_options(synchronize_session=False)
        )
        result = await self._db.exec(stmt)
        await self._db.commit()
        return int(result.rowcount)

    async def claim_batch(
        self, limit: int, *, lease_seconds: float, now: datetime
    ) -> list[ClaimedEmail]:
        """Take the next due messages off the queue and lease them to this sender.

        Args:
            limit: Maximum number of messages to claim.
            lease_seconds: How long the claim is good for before
                :meth:`reclaim_expired_leases` may take the messages back.
            now: The reference time due-ness and the lease are measured from.

        Returns:
            Snapshots of the claimed messages, oldest first, already moved to
            ``sending`` in the database.
        """
        stmt = (
            select(OutboundEmail)
            .where(
                col(OutboundEmail.status) == OutboundEmailStatus.pending,
                col(OutboundEmail.next_attempt_at) <= now,
            )
            .order_by(col(OutboundEmail.next_attempt_at).asc())
            .order_by(col(OutboundEmail.created_at).asc())
            .limit(limit)
        )
        result = await self._db.exec(stmt)
        rows = list(result.all())
        if not rows:
            return []
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        claimed = []
        for row in rows:
            row.status = OutboundEmailStatus.sending
            row.lease_expires_at = lease_expires_at
            self._db.add(row)
            claimed.append(
                ClaimedEmail(
                    id=row.id,
                    to_email=row.to_email,
                    subject=row.subject,
                    body=row.body,
                    attempts=row.attempts,
                )
            )
        await self._db.commit()
        return claimed

    async def mark_sent(self, email_id: str, *, sent_at: datetime) -> None:
        """Record that a message was accepted by the relay.

        Args:
            email_id: The claimed message that went out.
            sent_at: When the relay accepted it.
        """
        await self._settle(
            email_id,
            status=OutboundEmailStatus.sent,
            sent_at=sent_at,
            last_error=None,
        )

    async def reschedule(
        self, email_id: str, *, next_attempt_at: datetime, error: str
    ) -> None:
        """Return a message to the queue after a failure worth retrying.

        Args:
            email_id: The claimed message that failed.
            next_attempt_at: When it becomes eligible again.
            error: The failure reason, kept on the row for diagnosis.
        """
        await self._settle(
            email_id,
            status=OutboundEmailStatus.pending,
            next_attempt_at=next_attempt_at,
            last_error=error,
        )

    async def mark_failed(self, email_id: str, *, error: str) -> None:
        """Give up on a message and keep it as a dead letter.

        Args:
            email_id: The claimed message being abandoned.
            error: The failure reason that ended it.
        """
        await self._settle(
            email_id, status=OutboundEmailStatus.failed, last_error=error
        )

    async def _settle(self, email_id: str, **values: object) -> None:
        """Finish one attempt: apply the outcome, count it, and drop the lease.

        Counting the attempt in SQL rather than from a value read earlier keeps
        the increment honest no matter how stale the caller's snapshot is.

        Args:
            email_id: The message to settle.
            values: Columns the specific outcome sets.
        """
        stmt = (
            update(OutboundEmail)
            .where(col(OutboundEmail.id) == email_id)
            .values(
                attempts=col(OutboundEmail.attempts) + 1,
                lease_expires_at=None,
                **values,
            )
            .execution_options(synchronize_session=False)
        )
        await self._db.exec(stmt)
        await self._db.commit()

    async def purge_sent(self, *, before: datetime) -> int:
        """Delete delivered messages older than the retention cutoff.

        Only ``sent`` rows are eligible. ``failed`` rows are the dead-letter
        record and are kept until somebody looks at them.

        Args:
            before: Rows sent strictly earlier than this are removed.

        Returns:
            The number of rows deleted.
        """
        stmt = (
            delete(OutboundEmail)
            .where(
                col(OutboundEmail.status) == OutboundEmailStatus.sent,
                col(OutboundEmail.sent_at).is_not(None),
                col(OutboundEmail.sent_at) < before,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._db.exec(stmt)
        await self._db.commit()
        return int(result.rowcount)
