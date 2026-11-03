"""Tests for waking a session's stream viewers in ``services.session_stream``.

The poll interval is stretched to a minute throughout, so a frame that arrives
within a couple of seconds can only have come from a wake. The listener test
needs PostgreSQL and is skipped without ``A2FLOW_TEST_PG_URL``.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
import pytest_asyncio
from ag_ui.core import RunFinishedEvent
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_execution import WorkflowExecution
from services import session_stream
from services.session_stream import StreamWriter, run_stream_listener, stream_events
from tests._engine import PG_URL_ENV, make_test_engine, pg_url
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    seed_branch_session,
    seed_tenant,
    seed_users,
)

A = "session-a"
B = "session-b"

#: Long enough that no test passes by polling.
_WAIT = 2.0


@pytest_asyncio.fixture()
async def engine(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a database holding one run with sessions ``A`` and ``B``."""
    monkeypatch.setattr(session_stream, "_POLL_SECONDS", 60.0)
    monkeypatch.setattr(session_stream, "_viewers", {})
    monkeypatch.setattr(session_stream, "_listening", False)
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=A,
            name="wf",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            initiator_id="owner",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        execution_id = execution.id
        db.add(execution)
        await db.commit()
    await seed_branch_session(eng, execution_id, A)
    await seed_branch_session(eng, execution_id, B, parent_id=A)
    yield eng
    await eng.dispose()


async def _finish(eng: AsyncEngine, session_id: str) -> None:
    """Write a turn's last event to ``session_id``, as its writer would."""
    async with AsyncSession(eng) as db:
        await StreamWriter(db, session_id, "run-1").write(
            RunFinishedEvent(thread_id=session_id, run_id="run-1")
        )


async def _until(condition: Callable[[], bool]) -> None:
    """Yield to the loop until ``condition()`` holds, or fail after a while."""
    async with asyncio.timeout(_WAIT):
        while not condition():
            await asyncio.sleep(0.01)


class _Viewer:
    """One viewer of a session, counting the reads its stream makes."""

    def __init__(
        self,
        eng: AsyncEngine,
        session_id: str,
        disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        """Start streaming ``session_id`` from the beginning.

        Args:
            eng: The database to read through.
            session_id: The session to watch.
            disconnected: Called between a read that found nothing and the
                wait after it; by default the viewer never leaves.
        """
        self.reads = 0
        self._eng = eng
        self._frames = stream_events(
            session_id, 0, open_db=self._open, disconnected=disconnected or _stay
        )

    def _open(self) -> AsyncSession:
        self.reads += 1
        return AsyncSession(self._eng)

    async def next_frame(self) -> str:
        """Return the stream's next frame."""
        return await anext(self._frames)


async def _stay() -> bool:
    return False


async def test_a_write_wakes_only_its_own_sessions_viewers(engine: AsyncEngine) -> None:
    viewer = _Viewer(engine, A)
    first = asyncio.create_task(viewer.next_frame())
    await _until(lambda: viewer.reads == 1 and A in session_stream._viewers)

    await _finish(engine, B)
    await asyncio.sleep(0.2)
    assert viewer.reads == 1

    await _finish(engine, A)
    frame = await asyncio.wait_for(first, _WAIT)
    assert '"RUN_FINISHED"' in frame


async def test_a_write_between_the_read_and_the_wait_is_not_missed(
    engine: AsyncEngine,
) -> None:
    async def write_once_then_stay() -> bool:
        if viewer.reads == 1:
            await _finish(engine, A)
        return False

    viewer = _Viewer(engine, A, write_once_then_stay)
    frame = await asyncio.wait_for(viewer.next_frame(), _WAIT)
    assert '"RUN_FINISHED"' in frame


async def test_the_listener_wakes_viewers_on_another_replicas_write(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = pg_url()
    if url is None:
        pytest.skip(f"{PG_URL_ENV} is not set; LISTEN/NOTIFY needs PostgreSQL")
    monkeypatch.setattr(session_stream, "DB_URL", url)
    listen_engine = create_async_engine(
        url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    monkeypatch.setattr(session_stream, "dedicated_engine", lambda: listen_engine)
    listener = asyncio.create_task(run_stream_listener())
    try:
        await _until(lambda: session_stream._listening)
        viewer = _Viewer(engine, A)
        first = asyncio.create_task(viewer.next_frame())
        await _until(lambda: viewer.reads == 1)

        # With the listener up the writer wakes nobody itself, so only the
        # append's NOTIFY can deliver this.
        await _finish(engine, A)
        frame = await asyncio.wait_for(first, _WAIT)
        assert '"RUN_FINISHED"' in frame
    finally:
        listener.cancel()
        await asyncio.gather(listener, return_exceptions=True)
        await listen_engine.dispose()
