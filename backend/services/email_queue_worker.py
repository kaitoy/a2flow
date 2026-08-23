"""Drains the outgoing-email queue at a controlled rate, retrying what it can.

One process does this at a time. :func:`EmailQueueWorker.run_forever` holds the
``email-queue`` advisory lock (:func:`infrastructure.locks.email_queue_key`) for
as long as it runs and simply waits when another replica already has it, so a
horizontally scaled deployment still presents a single sender to the relay. That
is what makes two otherwise awkward things easy: the rate limiter is a plain
in-memory :class:`~infrastructure.rate_limit.TokenBucket` rather than something
shared through the database, and one SMTP connection can stay open for a whole
batch.

Each pass is :meth:`EmailQueueWorker.run_once`, which is also what the tests
drive; :meth:`run_forever` is that in a loop with a sleep. A pass reclaims
abandoned leases, resolves the relay configuration afresh (an admin may have
just fixed it), claims a batch, sends it one message at a time through the rate
limiter, and purges delivered messages past their retention.

Nothing here knows what a notification is. The message was rendered when it was
enqueued (see :mod:`services.notification_dispatch`); the worker's only
decisions are *when* to send and what to do about a failure.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.database import engine
from infrastructure.email_sender import SmtpEmailSender, SmtpSession, get_email_sender
from infrastructure.locks import LockNotAcquiredError, advisory_lock, email_queue_key
from infrastructure.rate_limit import TokenBucket
from infrastructure.secret_cipher import get_secret_cipher
from repositories import SqlSystemSettingsRepository
from repositories.exceptions import EmailSendError
from repositories.outbound_email_queue import ClaimedEmail, SqlOutboundEmailQueue
from services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)

#: Delay before the first retry, doubling from there. Short enough that a
#: momentary blip in the relay costs the recipient nothing they would notice.
_BASE_DELAY_SECONDS = 15.0

#: Ceiling on the retry delay. Past this the backoff stops doubling, so a long
#: outage is retried once an hour rather than drifting into next week.
_MAX_DELAY_SECONDS = 3600.0

#: Fraction the retry delay is randomly stretched or shrunk by. Spreads the
#: retries that pile up during an outage so they do not all land on the relay in
#: the same second when it comes back. Multiplicative, never down to zero: an
#: immediate retry the instant a relay recovers is how you knock it over again.
_JITTER_RATIO = 0.2

#: How long a claim is held before :meth:`SqlOutboundEmailQueue.
#: reclaim_expired_leases` may take it back. Comfortably longer than the SMTP
#: socket timeout times a batch, so a slow relay does not cause a sender to have
#: its own claims stolen out from under it.
_LEASE_SECONDS = 900.0


def backoff_delay(attempts: int, *, rng: random.Random) -> float:
    """Return how long to wait before the next attempt at a failed message.

    Args:
        attempts: Attempts already spent on this message, not counting the one
            being scheduled. Zero produces the first retry's delay.
        rng: Randomness source for the jitter. Injected so a test can make the
            result reproducible.

    Returns:
        The delay in seconds.
    """
    capped = min(_BASE_DELAY_SECONDS * 2.0**attempts, _MAX_DELAY_SECONDS)
    jitter: float = rng.uniform(1.0 - _JITTER_RATIO, 1.0 + _JITTER_RATIO)
    return capped * jitter


@dataclass(frozen=True)
class EmailQueueConfig:
    """Tunables for one worker, resolved from the environment at startup.

    Attributes:
        rate_per_second: Sustained messages per second handed to the relay.
        burst: Messages allowed back-to-back after an idle period.
        batch_size: Messages claimed per pass.
        poll_interval_seconds: Sleep between passes.
        max_attempts: Attempts a message gets before it becomes a dead letter.
        sent_retention_days: How long delivered messages are kept.
    """

    rate_per_second: float
    burst: int
    batch_size: int
    poll_interval_seconds: float
    max_attempts: int
    sent_retention_days: int

    @classmethod
    def from_settings(cls) -> "EmailQueueConfig":
        """Build the configuration from the application settings."""
        settings = get_settings()
        return cls(
            rate_per_second=settings.email_send_rate_per_second,
            burst=settings.email_send_burst,
            batch_size=settings.email_queue_batch_size,
            poll_interval_seconds=settings.email_queue_poll_interval_seconds,
            max_attempts=settings.email_max_attempts,
            sent_retention_days=settings.email_sent_retention_days,
        )


class EmailQueueWorker:
    """Sends queued notification email, one relay conversation at a time."""

    def __init__(
        self,
        config: EmailQueueConfig,
        *,
        sessions: Callable[[], AsyncSession] | None = None,
        sender: SmtpEmailSender | None = None,
        bucket: TokenBucket | None = None,
        now: Callable[[], datetime] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Wire a worker to its collaborators.

        The rate limiter belongs to the worker rather than to a pass: the limit
        applies to the relay over time, not to one batch, so it has to outlive
        one drain.

        Args:
            config: The tunables this worker runs with.
            sessions: Opens the database session one pass runs on. Defaults to a
                fresh session on the application engine, since the worker runs
                outside any request scope.
            sender: The SMTP adapter. Defaults to the process-wide singleton.
            bucket: The rate limiter. Defaults to one built from ``config``.
            now: Current time source. Injected so tests can pin it.
            rng: Randomness source for the retry jitter.
        """
        self._config = config
        self._sessions = sessions if sessions is not None else _new_session
        self._sender = sender if sender is not None else get_email_sender()
        self._now = now if now is not None else _utc_now
        self._rng = rng if rng is not None else random.Random()
        self._bucket = (
            bucket
            if bucket is not None
            else TokenBucket(config.rate_per_second, config.burst)
        )

    async def run_forever(self) -> None:
        """Drain the queue until cancelled, as the deployment's single sender.

        A replica that cannot take the lock is not an error — it is the expected
        state of every replica but one. It waits a poll interval and tries
        again, so if the holder dies its successor takes over within seconds.
        """
        while True:
            try:
                async with advisory_lock(email_queue_key(), wait_seconds=0):
                    logger.info("email queue worker is the active sender")
                    await self._drain_until_cancelled()
            except LockNotAcquiredError:
                await asyncio.sleep(self._config.poll_interval_seconds)

    async def _drain_until_cancelled(self) -> None:
        """Run passes back-to-back for as long as the lock is held."""
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A pass that blows up — the database went away, the settings
                # row is unreadable — must not end the sender. Log it and try
                # again after the usual pause.
                logger.exception("email queue drain pass failed")
            await asyncio.sleep(self._config.poll_interval_seconds)

    async def run_once(self) -> int:
        """Run one drain pass.

        Returns:
            How many messages were claimed and attempted. Zero when delivery is
            switched off or nothing was due.
        """
        async with self._sessions() as db:
            queue = SqlOutboundEmailQueue(db)
            await queue.reclaim_expired_leases(now=self._now())
            settings = SystemSettingsService(
                SqlSystemSettingsRepository(db), get_secret_cipher()
            )
            smtp_config = await settings.resolve_smtp()
            if smtp_config is None:
                return 0
            claimed = await queue.claim_batch(
                self._config.batch_size, lease_seconds=_LEASE_SECONDS, now=self._now()
            )
            if not claimed:
                await self._purge(queue)
                return 0
            sent = 0
            async with self._sender.session(smtp_config) as smtp:
                for email in claimed:
                    await self._bucket.take()
                    if await self._deliver(queue, smtp, email):
                        sent += 1
            await self._purge(queue)
            logger.info(
                "email queue pass: %d claimed, %d sent, %d left for later",
                len(claimed),
                sent,
                len(claimed) - sent,
            )
            return len(claimed)

    async def _deliver(
        self, queue: SqlOutboundEmailQueue, smtp: SmtpSession, email: ClaimedEmail
    ) -> bool:
        """Send one claimed message and record what happened to it.

        Args:
            queue: The queue the outcome is written back to.
            smtp: The open relay conversation.
            email: The claimed message.

        Returns:
            ``True`` if the relay accepted the message.
        """
        try:
            await smtp.send(to=email.to_email, subject=email.subject, body=email.body)
        except EmailSendError as exc:
            await self._settle_failure(queue, email, exc)
            return False
        await queue.mark_sent(email.id, sent_at=self._now())
        return True

    async def _settle_failure(
        self, queue: SqlOutboundEmailQueue, email: ClaimedEmail, exc: EmailSendError
    ) -> None:
        """Retry a message, or write it off when retrying cannot help.

        Args:
            queue: The queue the outcome is written back to.
            email: The claimed message that failed.
            exc: The failure, carrying whether it is worth another attempt.
        """
        spent = email.attempts + 1
        if exc.permanent or spent >= self._config.max_attempts:
            logger.error(
                "giving up on email %s after %d attempt(s): %s",
                email.id,
                spent,
                exc.reason,
            )
            await queue.mark_failed(email.id, error=exc.reason)
            return
        delay = backoff_delay(email.attempts, rng=self._rng)
        await queue.reschedule(
            email.id,
            next_attempt_at=self._now() + timedelta(seconds=delay),
            error=exc.reason,
        )

    async def _purge(self, queue: SqlOutboundEmailQueue) -> None:
        """Drop delivered messages that are past their retention window."""
        cutoff = self._now() - timedelta(days=self._config.sent_retention_days)
        purged = await queue.purge_sent(before=cutoff)
        if purged:
            logger.info("purged %d delivered email(s) older than %s", purged, cutoff)


def _new_session() -> AsyncSession:
    """Open a session on the application engine for one drain pass."""
    return AsyncSession(engine)


def _utc_now() -> datetime:
    """Return the current time, timezone-aware in UTC."""
    return datetime.now(UTC)


async def run_email_queue_worker() -> None:
    """Run a worker built from the environment until the task is cancelled.

    The entry point for both hosts of the worker: the dedicated ``worker``
    process and — when ``EMAIL_WORKER_IN_PROCESS`` is on — the API's lifespan.
    """
    worker = EmailQueueWorker(EmailQueueConfig.from_settings())
    with suppress(asyncio.CancelledError):
        await worker.run_forever()
