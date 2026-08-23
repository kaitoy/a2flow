"""Tests for the worker that drains the outgoing-email queue.

Driven through :meth:`EmailQueueWorker.run_once` with a fake relay and a pinned
clock, so what is being checked is the policy rather than any timing: what gets
sent, what gets retried and when, what gets written off, and what the rate
limiter is asked to allow.
"""

import random
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_settings, seed_system_user
from infrastructure.email_sender import SmtpConfig
from infrastructure.rate_limit import TokenBucket
from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailStatus,
)
from models.system_settings import SYSTEM_SETTINGS_ID, SmtpSecurity, SystemSettings
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID
from repositories.exceptions import EmailSendError
from repositories.outbound_email import SqlOutboundEmailRepository
from services.email_queue_worker import (
    _BASE_DELAY_SECONDS,
    _JITTER_RATIO,
    _MAX_DELAY_SECONDS,
    EmailQueueConfig,
    EmailQueueWorker,
    backoff_delay,
)

_TENANT_ID = "tenant-worker"
_NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


# ---------- backoff ----------


def test_the_first_retry_comes_after_the_base_delay() -> None:
    delay = backoff_delay(0, rng=random.Random(1))
    assert delay == pytest.approx(_BASE_DELAY_SECONDS, rel=_JITTER_RATIO)


@pytest.mark.parametrize("attempts", range(8))
def test_the_delay_stays_within_the_jitter_band(attempts: int) -> None:
    """Jitter spreads the retries but must never collapse one to nothing."""
    bare = min(_BASE_DELAY_SECONDS * 2.0**attempts, _MAX_DELAY_SECONDS)
    for seed in range(20):
        delay = backoff_delay(attempts, rng=random.Random(seed))
        assert bare * (1 - _JITTER_RATIO) <= delay <= bare * (1 + _JITTER_RATIO)


def test_the_delay_grows_with_every_failed_attempt() -> None:
    rng = random.Random(7)
    delays = [backoff_delay(attempts, rng=rng) for attempts in range(6)]
    assert delays == sorted(delays)


def test_the_delay_stops_growing_at_the_ceiling() -> None:
    """Otherwise a long outage would push the next attempt into next week."""
    assert backoff_delay(40, rng=random.Random(3)) <= _MAX_DELAY_SECONDS * (
        1 + _JITTER_RATIO
    )


def test_the_delay_is_scattered_across_calls() -> None:
    rng = random.Random(11)
    assert len({backoff_delay(3, rng=rng) for _ in range(10)}) > 1


# ---------- the drain pass ----------


class _FakeSmtpSession:
    """Records what was sent, and can be told to fail a given message."""

    def __init__(self, recorder: "_FakeSender") -> None:
        self._recorder = recorder

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """Record the message, or raise the failure scripted for this address."""
        failure = self._recorder.failures.get(to)
        if failure is not None:
            raise failure
        self._recorder.sent.append({"to": to, "subject": subject, "body": body})


class _FakeSender:
    """Stands in for the SMTP adapter, counting the connections it hands out."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.failures: dict[str, Exception] = {}
        self.sessions_opened = 0

    @asynccontextmanager
    async def session(self, config: SmtpConfig) -> AsyncIterator[_FakeSmtpSession]:
        """Hand out a recording session."""
        self.sessions_opened += 1
        yield _FakeSmtpSession(self)


@pytest_asyncio.fixture()
async def sessions() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """A session factory over one shared in-memory database.

    ``StaticPool`` is what makes the worker's own per-pass session see the rows
    the test seeded: without it every connection to ``:memory:`` gets a database
    of its own.
    """
    mem_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(
        mem_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as db:
        await seed_system_user(db)
        await seed_system_settings(db)
        db.add(
            Tenant(
                id=_TENANT_ID,
                display_name=_TENANT_ID,
                name=_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()
    yield factory
    await mem_engine.dispose()


async def _enable_smtp(
    sessions: async_sessionmaker[AsyncSession], **overrides: Any
) -> None:
    """Switch email delivery on with a complete configuration."""
    async with sessions() as db:
        settings = await db.get(SystemSettings, SYSTEM_SETTINGS_ID)
        assert settings is not None
        settings.smtp_enabled = True
        settings.smtp_host = "smtp.example.com"
        settings.smtp_port = 2525
        settings.smtp_security = SmtpSecurity.none
        settings.smtp_from_email = "a2flow@example.com"
        for key, value in overrides.items():
            setattr(settings, key, value)
        db.add(settings)
        await db.commit()


async def _enqueue(
    sessions: async_sessionmaker[AsyncSession],
    *,
    to_email: str = "recipient@example.com",
    **overrides: Any,
) -> str:
    """Stage one queued message and return its id."""
    async with sessions() as db:
        repo = SqlOutboundEmailRepository(db, tenant_id=_TENANT_ID)
        email = repo.stage(
            OutboundEmailCreate(
                to_email=to_email, subject="Approval requested", body="Please review."
            ),
            user_id=SYSTEM_USER_ID,
        )
        email.created_at = _NOW
        email.next_attempt_at = _NOW
        for key, value in overrides.items():
            setattr(email, key, value)
        await db.commit()
        return email.id


async def _row(
    sessions: async_sessionmaker[AsyncSession], email_id: str
) -> OutboundEmail:
    """Read one queue row back from the database."""
    async with sessions() as db:
        row = await db.get(OutboundEmail, email_id)
        assert row is not None
        return row


async def _rows(sessions: async_sessionmaker[AsyncSession]) -> list[OutboundEmail]:
    """Read every queue row back from the database, oldest first."""
    async with sessions() as db:
        result = await db.exec(
            select(OutboundEmail).order_by(col(OutboundEmail.created_at))
        )
        return list(result.all())


def _worker(
    sessions: async_sessionmaker[AsyncSession],
    sender: _FakeSender,
    *,
    bucket: TokenBucket | None = None,
    **config_overrides: Any,
) -> EmailQueueWorker:
    """Build a worker on the test database with a pinned clock and seeded jitter."""
    fields: dict[str, Any] = {
        "rate_per_second": 1000.0,
        "burst": 1000,
        "batch_size": 20,
        "poll_interval_seconds": 0.0,
        "max_attempts": 9,
        "sent_retention_days": 30,
    }
    fields.update(config_overrides)
    return EmailQueueWorker(
        EmailQueueConfig(**fields),
        sessions=sessions,
        sender=sender,  # type: ignore[arg-type]
        bucket=bucket,
        now=lambda: _NOW,
        rng=random.Random(0),
    )


async def test_a_due_message_is_sent_and_recorded(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    email_id = await _enqueue(sessions)
    sender = _FakeSender()

    assert await _worker(sessions, sender).run_once() == 1

    assert sender.sent == [
        {
            "to": "recipient@example.com",
            "subject": "Approval requested",
            "body": "Please review.",
        }
    ]
    row = await _row(sessions, email_id)
    assert row.status is OutboundEmailStatus.sent
    assert row.attempts == 1


async def test_nothing_is_claimed_while_delivery_is_switched_off(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A message must stay claimable, not be burned, while SMTP is unconfigured."""
    email_id = await _enqueue(sessions)
    sender = _FakeSender()

    assert await _worker(sessions, sender).run_once() == 0

    assert sender.sessions_opened == 0
    assert (await _row(sessions, email_id)).status is OutboundEmailStatus.pending


async def test_a_whole_batch_shares_one_connection(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    for index in range(3):
        await _enqueue(sessions, to_email=f"user{index}@example.com")
    sender = _FakeSender()

    await _worker(sessions, sender).run_once()

    assert sender.sessions_opened == 1
    assert len(sender.sent) == 3


async def test_the_batch_size_bounds_one_pass(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    for index in range(5):
        await _enqueue(sessions, to_email=f"user{index}@example.com")
    sender = _FakeSender()

    assert await _worker(sessions, sender, batch_size=2).run_once() == 2


async def test_every_message_passes_through_the_rate_limiter(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A backlog must not be able to burst straight past the relay's limit."""
    await _enable_smtp(sessions)
    for index in range(3):
        await _enqueue(sessions, to_email=f"user{index}@example.com")
    sender = _FakeSender()
    clock = _VirtualClock()
    # A bucket holding two permits and refilling slowly: the third message in
    # the batch cannot go out without waiting, which is what proves the worker
    # asks the limiter for every message rather than only between passes.
    bucket = TokenBucket(1.0, 2, clock=clock.time, sleep=clock.sleep)

    await _worker(sessions, sender, bucket=bucket).run_once()

    assert len(sender.sent) == 3
    assert clock.slept == [pytest.approx(1.0)]


async def test_a_transient_failure_is_scheduled_for_another_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    email_id = await _enqueue(sessions)
    sender = _FakeSender()
    sender.failures["recipient@example.com"] = EmailSendError("relay down")

    await _worker(sessions, sender).run_once()

    row = await _row(sessions, email_id)
    assert row.status is OutboundEmailStatus.pending
    assert row.attempts == 1
    assert row.last_error == "relay down"
    assert row.next_attempt_at.replace(tzinfo=UTC) > _NOW


async def test_the_retry_lands_within_the_backoff_window(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    email_id = await _enqueue(sessions)
    sender = _FakeSender()
    sender.failures["recipient@example.com"] = EmailSendError("relay down")

    await _worker(sessions, sender).run_once()

    row = await _row(sessions, email_id)
    delay = row.next_attempt_at.replace(tzinfo=UTC) - _NOW
    assert timedelta(seconds=_BASE_DELAY_SECONDS * (1 - _JITTER_RATIO)) <= delay
    assert delay <= timedelta(seconds=_BASE_DELAY_SECONDS * (1 + _JITTER_RATIO))


async def test_a_permanent_failure_is_written_off_on_the_first_attempt(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Retrying a refused recipient for an hour only delays the dead letter."""
    await _enable_smtp(sessions)
    email_id = await _enqueue(sessions)
    sender = _FakeSender()
    sender.failures["recipient@example.com"] = EmailSendError(
        "no such user", permanent=True
    )

    await _worker(sessions, sender).run_once()

    row = await _row(sessions, email_id)
    assert row.status is OutboundEmailStatus.failed
    assert row.attempts == 1


async def test_the_last_allowed_attempt_ends_in_a_dead_letter(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    email_id = await _enqueue(sessions, attempts=2)
    sender = _FakeSender()
    sender.failures["recipient@example.com"] = EmailSendError("relay down")

    await _worker(sessions, sender, max_attempts=3).run_once()

    row = await _row(sessions, email_id)
    assert row.status is OutboundEmailStatus.failed
    assert row.attempts == 3
    assert row.last_error == "relay down"


async def test_one_failure_does_not_stop_the_rest_of_the_batch(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    await _enqueue(sessions, to_email="broken@example.com")
    await _enqueue(sessions, to_email="fine@example.com")
    sender = _FakeSender()
    sender.failures["broken@example.com"] = EmailSendError("relay down")

    await _worker(sessions, sender).run_once()

    assert [message["to"] for message in sender.sent] == ["fine@example.com"]
    statuses = {row.to_email: row.status for row in await _rows(sessions)}
    assert statuses["fine@example.com"] is OutboundEmailStatus.sent
    assert statuses["broken@example.com"] is OutboundEmailStatus.pending


async def test_a_message_that_is_not_due_yet_is_left_alone(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    await _enqueue(sessions, next_attempt_at=_NOW + timedelta(minutes=5))
    sender = _FakeSender()

    assert await _worker(sessions, sender).run_once() == 0
    assert sender.sent == []


async def test_an_abandoned_lease_is_picked_up_by_the_next_pass(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """What a sender that died mid-batch left behind must not stay stuck."""
    await _enable_smtp(sessions)
    email_id = await _enqueue(
        sessions,
        status=OutboundEmailStatus.sending,
        lease_expires_at=_NOW - timedelta(seconds=1),
    )
    sender = _FakeSender()

    assert await _worker(sessions, sender).run_once() == 1
    assert (await _row(sessions, email_id)).status is OutboundEmailStatus.sent


async def test_delivered_messages_past_their_retention_are_purged(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _enable_smtp(sessions)
    old_id = await _enqueue(
        sessions,
        status=OutboundEmailStatus.sent,
        sent_at=_NOW - timedelta(days=31),
    )
    kept_id = await _enqueue(
        sessions, status=OutboundEmailStatus.failed, last_error="gave up"
    )
    sender = _FakeSender()

    await _worker(sessions, sender).run_once()

    remaining = {row.id for row in await _rows(sessions)}
    assert old_id not in remaining
    assert kept_id in remaining


class _VirtualClock:
    """A monotonic clock that advances only when something sleeps on it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        """Return the current virtual time, in seconds."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Advance the virtual clock instead of waiting."""
        self.slept.append(seconds)
        self.now += seconds
