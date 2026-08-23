"""A token bucket for pacing work against an external system's rate limit.

Written for one caller — :class:`services.email_queue_worker.EmailQueueWorker`,
which paces itself against the deployment's single SMTP relay — and deliberately
kept process-local rather than backed by the database. That is sound only
because exactly one process drains the queue at a time (see
:mod:`repositories.outbound_email_queue`); a rate limiter shared by N senders
would have to live somewhere both can see, and would only ever approximate the
limit. Keeping the sender single is what buys an exact one here.

The clock and the sleep are injectable so the pacing can be tested without
waiting for real time to pass.
"""

import asyncio
from collections.abc import Awaitable, Callable

#: How far below a whole token still counts as a whole token.
#:
#: Not cosmetic — it is what guarantees :meth:`TokenBucket.take` terminates.
#: Tokens are accumulated from differences between successive clock readings, so
#: after sleeping exactly long enough for one token the sum can land a few
#: units-in-the-last-place short of ``1.0``. The next wait computed from that
#: shortfall is then far too small to move the clock at all, and the loop spins
#: forever. A slack of a billionth of a token is nine orders of magnitude below
#: anything a mail relay could notice, and it makes progress unconditional.
_TOKEN_EPSILON = 1e-9


class TokenBucket:
    """Hands out permits at a fixed average rate, allowing short bursts.

    The bucket refills continuously at ``rate_per_second`` and holds at most
    ``burst`` permits, so a queue that has been idle can discharge up to
    ``burst`` messages immediately and then settles to the sustained rate.
    """

    def __init__(
        self,
        rate_per_second: float,
        burst: int,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Create a bucket that starts full.

        Starting full is the useful default here: the first messages after a
        quiet period should go out at once, not wait for a refill.

        Args:
            rate_per_second: Sustained permits per second. Must be positive.
            burst: Maximum permits the bucket holds. Must be at least one.
            clock: Monotonic time source, in seconds. Defaults to the running
                event loop's clock.
            sleep: Awaitable delay. Defaults to :func:`asyncio.sleep`.

        Raises:
            ValueError: If ``rate_per_second`` is not positive or ``burst`` is
                less than one — either would make :meth:`take` block forever.
        """
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self._rate = rate_per_second
        self._burst = float(burst)
        self._clock = clock if clock is not None else _loop_time
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._tokens = float(burst)
        self._updated = self._clock()

    async def take(self) -> None:
        """Wait until a permit is available, then consume it."""
        while True:
            self._refill()
            if self._tokens >= 1.0 - _TOKEN_EPSILON:
                self._tokens = max(self._tokens - 1.0, 0.0)
                return
            await self._sleep((1.0 - self._tokens) / self._rate)

    def _refill(self) -> None:
        """Credit the tokens earned since the last check, up to the burst cap."""
        now = self._clock()
        elapsed = max(now - self._updated, 0.0)
        self._updated = now
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)


def _loop_time() -> float:
    """Return the running event loop's monotonic clock, in seconds.

    The loop's clock rather than :func:`time.monotonic` so a test driving the
    loop with a virtual clock sees the same time the bucket does.
    """
    return asyncio.get_running_loop().time()
