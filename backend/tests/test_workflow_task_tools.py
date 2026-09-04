"""Tests for the WorkflowTask agent tools in ``infrastructure.workflow_task_tools``.

The tools open their own ``AsyncSession`` on ``infrastructure.database.engine``;
each test monkeypatches that engine to a throwaway database and
drives the tools with a lightweight fake ToolContext exposing only ``session.id``
and ``user_id`` (the attributes the tools read).

The execution agent can only advance a task's status, so the tools under test are
``list_workflow_tasks`` / ``get_workflow_task`` / ``update_workflow_task``. Tasks
a test needs to already exist are seeded straight into the table with
:func:`tests._seed.seed_workflow_task`, standing in for the run-time copy a real
execution makes from the workflow's published templates.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.workflow_task_tools import (
    ACTING_USER_STATE_KEY,
    _resolve_scope,
    get_workflow_task,
    list_workflow_tasks,
    update_workflow_task,
)
from models.notification import Notification, NotificationType
from models.workflow_execution import WorkflowExecution, WorkflowExecutionStatus
from models.workflow_task import WorkflowTask
from repositories import SqlNotificationRepository, SqlWorkflowExecutionRepository
from repositories.tenant_bootstrap import NoTenantSessionError
from tests._engine import make_test_engine
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    seed_tenant,
    seed_users,
    seed_workflow_task,
)


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the tools' module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_session(
    eng: AsyncEngine,
    *,
    session_id: str = "sess-abc",
    user_id: str = "owner",
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a WorkflowExecution with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=session_id,
            name="wf",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            initiator_id=user_id,
            tenant_id=tenant_id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


def _ctx(
    session_id: str = "sess-abc",
    user_id: str = "tester",
    *,
    state: dict[str, Any] | None = None,
) -> Any:
    """Build a fake ToolContext exposing ``session.id``, ``user_id``, and ``state``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=user_id, state=state
    )


async def test_update_workflow_task_attributes_to_acting_user(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_session(engine, user_id="owner")
    task_id = await seed_workflow_task(engine, execution_id, title="Solo")
    await update_workflow_task(
        task_id,
        _ctx(user_id="owner", state={ACTING_USER_STATE_KEY: "bob"}),
        status="in_progress",
    )
    async with AsyncSession(engine) as db:
        task = await db.get(WorkflowTask, task_id)
    assert task is not None
    assert task.created_by == "owner"
    assert task.updated_by == "bob"


async def test_list_isolates_sessions(engine: AsyncEngine) -> None:
    execution_a = await _seed_session(engine, session_id="sess-a")
    execution_b = await _seed_session(engine, session_id="sess-b")
    await seed_workflow_task(engine, execution_a, title="In A")
    await seed_workflow_task(engine, execution_b, title="In B")
    listed_a = await list_workflow_tasks(_ctx("sess-a"))
    assert [t["title"] for t in listed_a["tasks"]] == ["In A"]


async def test_get_workflow_task_cross_session_guard(
    engine: AsyncEngine,
) -> None:
    execution_a = await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    task_id = await seed_workflow_task(engine, execution_a, title="Owned by A")

    blocked = await get_workflow_task(task_id, _ctx("sess-b"))
    assert "error" in blocked
    allowed = await get_workflow_task(task_id, _ctx("sess-a"))
    assert allowed["id"] == task_id


async def test_update_status(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine)
    task_id = await seed_workflow_task(engine, execution_id, title="Task")
    updated = await update_workflow_task(task_id, _ctx(), status="in_progress")
    assert updated["status"] == "in_progress"


async def test_update_invalid_status(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine)
    task_id = await seed_workflow_task(engine, execution_id, title="Task")
    result = await update_workflow_task(task_id, _ctx(), status="nope")
    assert "error" in result


async def test_update_preserves_unset_fields(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine)
    task_id = await seed_workflow_task(
        engine, execution_id, title="Original", description="desc"
    )
    updated = await update_workflow_task(task_id, _ctx(), status="completed")
    assert updated["title"] == "Original"
    assert updated["description"] == "desc"
    assert updated["status"] == "completed"


async def test_resolve_scope(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine, session_id="sess-x")
    async with AsyncSession(engine) as db:
        assert await _resolve_scope(_ctx("sess-x"), db) == (
            execution_id,
            DEFAULT_TEST_TENANT_ID,
        )
        with pytest.raises(NoTenantSessionError):
            await _resolve_scope(_ctx("absent"), db)


async def test_get_by_session_id(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine, session_id="sess-find")
    async with AsyncSession(engine) as db:
        repo = SqlWorkflowExecutionRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        found = await repo.get_by_session_id("sess-find")
        assert found is not None
        assert found.id == execution_id
        assert await repo.get_by_session_id("absent") is None


async def _notifications_for(eng: AsyncEngine, user_id: str) -> list[Notification]:
    """Return all notifications addressed to ``user_id`` via the repository."""
    async with AsyncSession(eng) as db:
        repo = SqlNotificationRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        return await repo.list(user_id=user_id, limit=100, offset=0)


async def test_execution_completed_notification_emitted_once(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_session(engine, user_id="owner")
    a = await seed_workflow_task(engine, execution_id, title="A")
    b = await seed_workflow_task(engine, execution_id, title="B")

    # Not every task is terminal yet: no completion notification.
    await update_workflow_task(a, _ctx(), status="completed")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.execution_completed
    ]
    assert completed == []

    # Final task reaches a terminal state: exactly one completion notification.
    await update_workflow_task(b, _ctx(), status="failed")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.execution_completed
    ]
    assert len(completed) == 1

    # A further terminal-state update must not create a duplicate.
    await update_workflow_task(a, _ctx(), status="skipped")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.execution_completed
    ]
    assert len(completed) == 1


# ---------- tenant isolation ----------


async def test_get_workflow_task_cross_tenant_guard(engine: AsyncEngine) -> None:
    """A task seeded under one tenant's session is invisible from another's.

    Both sessions use distinct ADK session ids (the normal case): the tenant
    boundary is enforced by the resolved tenant id, not by session-id
    collision, so this confirms the bootstrap-resolution path picks the
    correct tenant for each call and that the underlying repositories filter
    on it.
    """
    await seed_tenant(engine, "tenant-other")
    execution_a = await _seed_session(
        engine, session_id="sess-tenant-a", tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _seed_session(engine, session_id="sess-tenant-b", tenant_id="tenant-other")
    task_id = await seed_workflow_task(engine, execution_a, title="Tenant A's task")

    blocked = await get_workflow_task(task_id, _ctx("sess-tenant-b"))
    assert "error" in blocked
    allowed = await get_workflow_task(task_id, _ctx("sess-tenant-a"))
    assert allowed["id"] == task_id


async def _execution(eng: AsyncEngine, execution_id: str) -> WorkflowExecution:
    """Return the run, re-read so its lifecycle fields are current."""
    async with AsyncSession(eng) as db:
        repo = SqlWorkflowExecutionRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        execution = await repo.get(execution_id)
        assert execution is not None
        return execution


async def test_agent_completing_every_task_finishes_the_run(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_session(engine, user_id="owner")
    a = await seed_workflow_task(engine, execution_id, title="A")
    b = await seed_workflow_task(engine, execution_id, title="B")

    await update_workflow_task(a, _ctx(), status="completed")
    assert (
        await _execution(engine, execution_id)
    ).status is WorkflowExecutionStatus.running

    await update_workflow_task(b, _ctx(), status="completed")
    finished = await _execution(engine, execution_id)
    assert finished.status is WorkflowExecutionStatus.completed
    assert finished.finished_at is not None


async def test_agent_failing_a_task_fails_the_run(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine, user_id="owner")
    task_id = await seed_workflow_task(engine, execution_id, title="A")

    await update_workflow_task(
        task_id,
        _ctx(),
        status="failed",
        error_kind="timeout",
        error_message="no response after 30s",
    )

    finished = await _execution(engine, execution_id)
    assert finished.status is WorkflowExecutionStatus.failed
    assert finished.finished_at is not None


async def test_agent_records_the_failure_cause(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine, user_id="owner")
    task_id = await seed_workflow_task(engine, execution_id, title="A")

    updated = await update_workflow_task(
        task_id,
        _ctx(),
        status="failed",
        error_kind="api_error",
        error_message="billing API returned 503",
    )

    assert updated["error_kind"] == "api_error"
    assert updated["error_message"] == "billing API returned 503"


async def test_agent_unknown_error_kind_is_rejected(engine: AsyncEngine) -> None:
    """An invalid classification is reported back to the model, listing the valid ones."""
    execution_id = await _seed_session(engine, user_id="owner")
    task_id = await seed_workflow_task(engine, execution_id, title="A")

    result = await update_workflow_task(
        task_id, _ctx(), status="failed", error_kind="disk_on_fire"
    )

    assert "invalid error_kind" in result["error"]
    assert "script_error" in result["error"]
    # The rejected call wrote nothing at all.
    assert (
        await _execution(engine, execution_id)
    ).status is WorkflowExecutionStatus.running
