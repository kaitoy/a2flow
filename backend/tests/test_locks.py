"""Tests for the cross-process run lock in ``infrastructure.locks``.

The suite runs against the SQLite ``DB_URL``, so ``advisory_lock`` takes its
in-process branch. That branch is the one a single-process deployment actually
uses, and it enforces the same contract as the PostgreSQL advisory lock, so the
mutual-exclusion behavior asserted here is the behavior both backends promise.
The key-derivation tests below apply to both.
"""

import asyncio

import pytest

from infrastructure.locks import (
    LockNotAcquiredError,
    _local_locks,
    _local_waiters,
    advisory_lock,
    agent_run_key,
    lock_id,
)


def test_agent_run_key_joins_the_session_coordinates() -> None:
    assert agent_run_key("A2Flow", "user-1", "thread-1") == "A2Flow:user-1:thread-1"


def test_lock_id_is_stable_across_processes() -> None:
    """The digest must not drift: a changed hash splits the lock on a rolling deploy.

    A pinned expected value, not just a self-consistency check — recomputing it
    from the same function would pass even if the algorithm changed underneath.
    """
    assert lock_id("A2Flow:user-1:thread-1") == 1_421_996_469_691_384_073


def test_lock_id_fits_in_a_signed_64_bit_integer() -> None:
    ids = [lock_id(f"A2Flow:user-1:thread-{i}") for i in range(200)]
    assert all(-(2**63) <= value < 2**63 for value in ids)


def test_lock_id_separates_distinct_keys() -> None:
    assert lock_id("A2Flow:user-1:thread-1") != lock_id("A2Flow:user-1:thread-2")
    assert lock_id("A2Flow:user-1:thread-1") != lock_id("A2Flow:user-2:thread-1")


async def test_advisory_lock_excludes_a_second_holder_of_the_same_key() -> None:
    async with advisory_lock("A2Flow:user-1:thread-1"):
        with pytest.raises(LockNotAcquiredError) as exc_info:
            async with advisory_lock("A2Flow:user-1:thread-1", wait_seconds=0.05):
                pytest.fail("the lock was granted twice at once")
    assert exc_info.value.key == "A2Flow:user-1:thread-1"


async def test_advisory_lock_releases_on_exit() -> None:
    async with advisory_lock("A2Flow:user-1:thread-1"):
        pass
    async with advisory_lock("A2Flow:user-1:thread-1", wait_seconds=0.05):
        pass


async def test_advisory_lock_releases_when_the_body_raises() -> None:
    with pytest.raises(RuntimeError):
        async with advisory_lock("A2Flow:user-1:thread-1"):
            raise RuntimeError("boom")
    async with advisory_lock("A2Flow:user-1:thread-1", wait_seconds=0.05):
        pass


async def test_advisory_lock_does_not_serialize_distinct_keys() -> None:
    async with (
        advisory_lock("A2Flow:user-1:thread-1"),
        advisory_lock("A2Flow:user-1:thread-2", wait_seconds=0.05),
        advisory_lock("A2Flow:user-2:thread-1", wait_seconds=0.05),
    ):
        pass


async def test_advisory_lock_waits_for_the_holder_rather_than_failing_fast() -> None:
    """A contended lock is granted once the holder lets go, within the wait budget.

    This is what keeps a client that aborts a stream and immediately retries from
    being rejected while the abandoned run's teardown is still unwinding.
    """
    acquired = asyncio.Event()
    released = asyncio.Event()

    async def hold_briefly() -> None:
        async with advisory_lock("A2Flow:user-1:thread-1"):
            acquired.set()
            await asyncio.sleep(0.1)
        released.set()

    holder = asyncio.create_task(hold_briefly())
    await acquired.wait()

    async with advisory_lock("A2Flow:user-1:thread-1", wait_seconds=5.0):
        assert released.is_set()
    await holder


async def test_advisory_lock_serializes_concurrent_runs_of_one_session() -> None:
    """Concurrent holders never overlap, and each waits its turn."""
    concurrent = 0
    peak = 0

    async def run() -> None:
        nonlocal concurrent, peak
        async with advisory_lock("A2Flow:user-1:thread-1", wait_seconds=5.0):
            concurrent += 1
            peak = max(peak, concurrent)
            await asyncio.sleep(0.01)
            concurrent -= 1

    await asyncio.gather(*(run() for _ in range(5)))
    assert peak == 1


async def test_advisory_lock_does_not_leak_registry_entries() -> None:
    """The in-process registry is emptied once the last holder and waiter are gone.

    Without this, a long-lived process accumulates one lock object per session it
    has ever run.
    """
    locks_before = dict(_local_locks)
    waiters_before = dict(_local_waiters)

    for i in range(10):
        async with advisory_lock(f"A2Flow:user-1:thread-{i}"):
            pass

    assert _local_locks == locks_before
    assert _local_waiters == waiters_before
