"""Tests for the outgoing-email queue's persistence layer.

The queue is the only thing standing between a notification and a lost email,
so its state machine is tested directly rather than through the worker: what is
claimable and in what order, what a lease does when a sender dies, how a
failure schedules the next attempt, and what the retention purge is allowed to
delete.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest_asyncio
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailStatus,
)
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID
from repositories.outbound_email import SqlOutboundEmailRepository
from repositories.outbound_email_queue import SqlOutboundEmailQueue
from tests._engine import make_test_engine

_TENANT_ID = "tenant-queue"
_OTHER_TENANT_ID = "tenant-other"
_NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture()
async def session() -> AsyncGenerator[AsyncSession, None]:
    """A throwaway database session with the schema and baseline rows in place."""
    mem_engine = await make_test_engine()
    async with AsyncSession(mem_engine) as db:
        await seed_system_user(db)
        for tenant_id in (_TENANT_ID, _OTHER_TENANT_ID):
            db.add(
                Tenant(
                    id=tenant_id,
                    display_name=tenant_id,
                    name=tenant_id,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
        await db.commit()
        yield db
    await mem_engine.dispose()


async def _enqueue(
    session: AsyncSession, *, tenant_id: str = _TENANT_ID, **overrides: Any
) -> OutboundEmail:
    """Stage and commit one queued message, applying any column overrides.

    The scheduling columns are pinned to ``_NOW`` rather than left at their
    wall-clock defaults so every assertion about due-ness is deterministic.
    """
    repo = SqlOutboundEmailRepository(session, tenant_id=tenant_id)
    email = repo.stage(
        OutboundEmailCreate(
            to_email="recipient@example.com",
            subject="Approval requested",
            body="Please review.",
        ),
        user_id=SYSTEM_USER_ID,
    )
    email.created_at = _NOW
    email.next_attempt_at = _NOW
    for key, value in overrides.items():
        setattr(email, key, value)
    await session.commit()
    await session.refresh(email)
    return email


async def _rows(session: AsyncSession) -> list[OutboundEmail]:
    """Return every queue row, oldest first, freshly read from the database."""
    session.expunge_all()
    result = await session.exec(
        select(OutboundEmail).order_by(col(OutboundEmail.created_at))
    )
    return list(result.all())


async def _statuses(session: AsyncSession) -> list[OutboundEmailStatus]:
    """Return the status of every queue row, oldest first."""
    return [row.status for row in await _rows(session)]


async def _row(session: AsyncSession, email_id: str) -> OutboundEmail:
    """Return one queue row, freshly read from the database."""
    session.expunge_all()
    row = await session.get(OutboundEmail, email_id)
    assert row is not None
    return row


async def test_stage_starts_a_message_pending_and_immediately_due(
    session: AsyncSession,
) -> None:
    email = await _enqueue(session)

    assert email.status is OutboundEmailStatus.pending
    assert email.attempts == 0
    assert email.sent_at is None
    assert email.lease_expires_at is None


async def test_claim_takes_due_messages_oldest_first(session: AsyncSession) -> None:
    later_id = (await _enqueue(session, next_attempt_at=_NOW - timedelta(minutes=1))).id
    earlier_id = (
        await _enqueue(session, next_attempt_at=_NOW - timedelta(minutes=5))
    ).id
    queue = SqlOutboundEmailQueue(session)

    claimed = await queue.claim_batch(10, lease_seconds=60, now=_NOW)

    assert [email.id for email in claimed] == [earlier_id, later_id]
    assert await _statuses(session) == [OutboundEmailStatus.sending] * 2


async def test_claim_leaves_messages_that_are_not_due_yet(
    session: AsyncSession,
) -> None:
    await _enqueue(session, next_attempt_at=_NOW + timedelta(seconds=1))
    queue = SqlOutboundEmailQueue(session)

    assert await queue.claim_batch(10, lease_seconds=60, now=_NOW) == []


async def test_claim_honours_the_batch_limit(session: AsyncSession) -> None:
    for _ in range(3):
        await _enqueue(session)
    queue = SqlOutboundEmailQueue(session)

    assert len(await queue.claim_batch(2, lease_seconds=60, now=_NOW)) == 2


async def test_claim_crosses_tenants(session: AsyncSession) -> None:
    """One relay drains everything; a tenant boundary must not hide a message."""
    await _enqueue(session, tenant_id=_TENANT_ID)
    await _enqueue(session, tenant_id=_OTHER_TENANT_ID)
    queue = SqlOutboundEmailQueue(session)

    claimed = await queue.claim_batch(10, lease_seconds=60, now=_NOW)

    assert len(claimed) == 2
    assert {row.tenant_id for row in await _rows(session)} == {
        _TENANT_ID,
        _OTHER_TENANT_ID,
    }


async def test_a_claimed_message_is_not_claimed_again(session: AsyncSession) -> None:
    await _enqueue(session)
    queue = SqlOutboundEmailQueue(session)
    await queue.claim_batch(10, lease_seconds=60, now=_NOW)

    assert await queue.claim_batch(10, lease_seconds=60, now=_NOW) == []


async def test_claim_sets_a_lease_that_expires(session: AsyncSession) -> None:
    await _enqueue(session)
    queue = SqlOutboundEmailQueue(session)

    claimed = await queue.claim_batch(1, lease_seconds=90, now=_NOW)

    leased = await _row(session, claimed[0].id)
    assert leased.lease_expires_at is not None
    assert leased.lease_expires_at.replace(tzinfo=UTC) == _NOW + timedelta(seconds=90)


async def test_an_expired_lease_returns_the_message_to_the_queue(
    session: AsyncSession,
) -> None:
    """A sender that dies mid-batch must not strand its claim forever."""
    await _enqueue(session)
    queue = SqlOutboundEmailQueue(session)
    await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    reclaimed = await queue.reclaim_expired_leases(now=_NOW + timedelta(seconds=61))

    assert reclaimed == 1
    assert len(await queue.claim_batch(1, lease_seconds=60, now=_NOW)) == 1


async def test_a_live_lease_is_left_alone(session: AsyncSession) -> None:
    await _enqueue(session)
    queue = SqlOutboundEmailQueue(session)
    await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    assert await queue.reclaim_expired_leases(now=_NOW + timedelta(seconds=59)) == 0


async def test_reclaiming_does_not_consume_the_retry_budget(
    session: AsyncSession,
) -> None:
    email_id = (await _enqueue(session)).id
    queue = SqlOutboundEmailQueue(session)
    await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    await queue.reclaim_expired_leases(now=_NOW + timedelta(seconds=61))

    assert (await _row(session, email_id)).attempts == 0


async def test_a_claim_reports_the_attempts_already_spent(
    session: AsyncSession,
) -> None:
    """The worker computes its backoff from this, so it must exclude the try ahead."""
    await _enqueue(session, attempts=3)
    queue = SqlOutboundEmailQueue(session)

    claimed = await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    assert claimed[0].attempts == 3


async def test_mark_sent_records_the_delivery(session: AsyncSession) -> None:
    email_id = (await _enqueue(session)).id
    queue = SqlOutboundEmailQueue(session)
    claimed = await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    await queue.mark_sent(claimed[0].id, sent_at=_NOW)

    email = await _row(session, email_id)
    assert email.status is OutboundEmailStatus.sent
    assert email.attempts == 1
    assert email.sent_at is not None
    assert email.lease_expires_at is None


async def test_reschedule_returns_the_message_with_a_later_due_time(
    session: AsyncSession,
) -> None:
    email_id = (await _enqueue(session)).id
    queue = SqlOutboundEmailQueue(session)
    claimed = await queue.claim_batch(1, lease_seconds=60, now=_NOW)
    due = _NOW + timedelta(seconds=15)

    await queue.reschedule(claimed[0].id, next_attempt_at=due, error="relay down")

    email = await _row(session, email_id)
    assert email.status is OutboundEmailStatus.pending
    assert email.attempts == 1
    assert email.last_error == "relay down"
    assert email.next_attempt_at.replace(tzinfo=UTC) == due
    assert await queue.claim_batch(1, lease_seconds=60, now=_NOW) == []
    assert len(await queue.claim_batch(1, lease_seconds=60, now=due)) == 1


async def test_mark_failed_keeps_the_message_as_a_dead_letter(
    session: AsyncSession,
) -> None:
    email_id = (await _enqueue(session)).id
    queue = SqlOutboundEmailQueue(session)
    claimed = await queue.claim_batch(1, lease_seconds=60, now=_NOW)

    await queue.mark_failed(claimed[0].id, error="mailbox unavailable")

    email = await _row(session, email_id)
    assert email.status is OutboundEmailStatus.failed
    assert email.last_error == "mailbox unavailable"
    assert await queue.claim_batch(1, lease_seconds=60, now=_NOW) == []


async def test_purge_removes_only_delivered_messages_past_the_cutoff(
    session: AsyncSession,
) -> None:
    # Each id is read straight off the freshly refreshed instance: the next
    # commit expires every earlier one, and a deleted row can no longer reload.
    old_id = (
        await _enqueue(
            session,
            status=OutboundEmailStatus.sent,
            sent_at=_NOW - timedelta(days=31),
        )
    ).id
    recent_id = (
        await _enqueue(
            session, status=OutboundEmailStatus.sent, sent_at=_NOW - timedelta(days=1)
        )
    ).id
    dead_id = (await _enqueue(session, status=OutboundEmailStatus.failed)).id
    queue = SqlOutboundEmailQueue(session)

    purged = await queue.purge_sent(before=_NOW - timedelta(days=30))

    assert purged == 1
    assert await session.get(OutboundEmail, old_id) is None
    assert await session.get(OutboundEmail, recent_id) is not None
    assert await session.get(OutboundEmail, dead_id) is not None


async def test_counts_by_status_reports_zero_for_empty_statuses(
    session: AsyncSession,
) -> None:
    """A drained queue must still export a series, not make it disappear."""
    await _enqueue(session)
    repo = SqlOutboundEmailRepository(session, tenant_id=_TENANT_ID)

    counts = await repo.counts_by_status()

    assert counts == {
        OutboundEmailStatus.pending: 1,
        OutboundEmailStatus.sending: 0,
        OutboundEmailStatus.sent: 0,
        OutboundEmailStatus.failed: 0,
    }


async def test_counts_by_status_is_scoped_to_one_tenant(
    session: AsyncSession,
) -> None:
    await _enqueue(session, tenant_id=_OTHER_TENANT_ID)
    repo = SqlOutboundEmailRepository(session, tenant_id=_TENANT_ID)

    assert (await repo.counts_by_status())[OutboundEmailStatus.pending] == 0


async def test_oldest_pending_age_counts_messages_stuck_mid_send(
    session: AsyncSession,
) -> None:
    """A hung relay leaves rows in `sending`; the backlog must still show it."""
    await _enqueue(session, created_at=_NOW - timedelta(seconds=120))
    queue = SqlOutboundEmailQueue(session)
    await queue.claim_batch(1, lease_seconds=600, now=_NOW)
    repo = SqlOutboundEmailRepository(session, tenant_id=_TENANT_ID)

    assert await repo.oldest_pending_age_seconds(now=_NOW) == 120.0


async def test_oldest_pending_age_is_none_when_nothing_is_waiting(
    session: AsyncSession,
) -> None:
    repo = SqlOutboundEmailRepository(session, tenant_id=_TENANT_ID)

    assert await repo.oldest_pending_age_seconds(now=_NOW) is None
