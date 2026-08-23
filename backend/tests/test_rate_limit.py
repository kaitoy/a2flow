"""Tests for the token bucket that paces sends against the SMTP relay.

Driven by a virtual clock rather than real time: the properties worth pinning
down are "a burst goes out at once", "the sustained rate is respected", and "an
idle period refills but never past the cap", none of which should cost a test
run any wall-clock seconds.
"""

import pytest

from infrastructure.rate_limit import TokenBucket

#: Sleeps allowed in one test before the clock decides the bucket is spinning.
#: A virtual clock cannot be advanced by a wait shorter than its own floating
#: point resolution, so a bucket that computes such a wait would hang the whole
#: test run rather than fail; this turns that into an assertion.
_RUNAWAY_SLEEPS = 100


class _VirtualClock:
    """A monotonic clock that only advances when something sleeps on it."""

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
        if len(self.slept) > _RUNAWAY_SLEEPS:
            raise AssertionError(
                f"bucket slept {len(self.slept)} times without making progress; "
                f"last waits were {self.slept[-5:]}"
            )

    def advance(self, seconds: float) -> None:
        """Move the clock forward without anyone having slept."""
        self.now += seconds


def _bucket(rate: float, burst: int, clock: _VirtualClock) -> TokenBucket:
    """Build a bucket wired to the virtual clock."""
    return TokenBucket(rate, burst, clock=clock.time, sleep=clock.sleep)


async def test_a_full_bucket_hands_out_its_burst_without_waiting() -> None:
    clock = _VirtualClock()
    bucket = _bucket(1.0, 3, clock)

    for _ in range(3):
        await bucket.take()

    assert clock.slept == []


async def test_the_next_permit_after_a_burst_waits_for_a_refill() -> None:
    clock = _VirtualClock()
    bucket = _bucket(2.0, 1, clock)
    await bucket.take()

    await bucket.take()

    assert clock.slept == [pytest.approx(0.5)]


async def test_the_sustained_rate_is_respected_over_many_permits() -> None:
    """Ten permits from an empty-after-one bucket at 5/s take about two seconds.

    Also the regression guard for a bucket that accumulates rounding error until
    the wait it computes is too small to advance any clock: that used to spin
    forever here rather than fail.
    """
    clock = _VirtualClock()
    bucket = _bucket(5.0, 1, clock)

    for _ in range(10):
        await bucket.take()

    assert clock.now == pytest.approx(9 / 5.0)
    assert len(clock.slept) == 9


async def test_idle_time_refills_the_bucket() -> None:
    clock = _VirtualClock()
    bucket = _bucket(10.0, 5, clock)
    for _ in range(5):
        await bucket.take()

    clock.advance(0.3)
    for _ in range(3):
        await bucket.take()

    assert clock.slept == []


async def test_a_long_idle_period_never_fills_past_the_burst() -> None:
    """Otherwise a quiet night would let the whole backlog out at once."""
    clock = _VirtualClock()
    bucket = _bucket(1.0, 2, clock)
    for _ in range(2):
        await bucket.take()

    clock.advance(3600)
    for _ in range(2):
        await bucket.take()
    await bucket.take()

    assert clock.slept == [pytest.approx(1.0)]


@pytest.mark.parametrize(("rate", "burst"), [(0.0, 1), (-1.0, 1), (1.0, 0)])
def test_a_bucket_that_could_never_hand_out_a_permit_is_rejected(
    rate: float, burst: int
) -> None:
    with pytest.raises(ValueError):
        TokenBucket(rate, burst)
