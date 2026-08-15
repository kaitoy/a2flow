"""Tests for the workflow operations metrics.

Covers both faces of the feature: the Prometheus exposition at
``GET /api/v1/metrics`` and the aggregate sub-resources on the
workflow-execution and approval routers. Every test seeds rows directly rather
than driving a run end to end, so the assertions are about the aggregation
itself and not about the agent.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.approval import Approval, ApprovalStatus
from models.workflow import Workflow, WorkflowStatus
from models.workflow_execution import WorkflowExecution, WorkflowExecutionStatus
from models.workflow_task import TaskErrorKind, WorkflowTask, WorkflowTaskStatus
from tests._envelope import assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

OTHER_TENANT_ID = "tenant-other"


@pytest_asyncio.fixture()
async def metrics_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and the engine backing it, with two tenants seeded."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)
    await seed_tenant(mem_engine)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _seed_skill(
    eng: AsyncEngine, *, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> str:
    """Insert the AgentSkill a Workflow's foreign key requires, and return its id."""
    skill_id = f"skill-{tenant_id}"
    async with AsyncSession(eng) as db:
        if await db.get(AgentSkill, skill_id) is not None:
            return skill_id
        db.add(
            AgentSkill(
                id=skill_id,
                name=skill_id,
                repo_url="https://example.com/repo",
                repo_path=".",
                tenant_id=tenant_id,
                created_by="owner",
                updated_by="owner",
            )
        )
        await db.commit()
    return skill_id


async def _seed_workflow(
    eng: AsyncEngine, *, name: str, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> str:
    """Insert a Workflow (and the AgentSkill it references) and return its primary key."""
    skill_id = await _seed_skill(eng, tenant_id=tenant_id)
    async with AsyncSession(eng) as db:
        workflow = Workflow(
            name=name,
            agent_skill_id=skill_id,
            session_id=f"design-{name}",
            agent_skill_commit_sha="deadbeef",
            status=WorkflowStatus.published,
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow.id


async def _seed_execution(
    eng: AsyncEngine,
    *,
    workflow_id: str | None,
    name: str = "run",
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.running,
    created_at: datetime | None = None,
    finished_at: datetime | None = None,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a WorkflowExecution with explicit lifecycle fields and return its id."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=f"sess-{name}",
            name=name,
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            initiator_id="owner",
            workflow_id=workflow_id,
            status=status,
            created_at=created_at or datetime.now(UTC),
            finished_at=finished_at,
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_task(
    eng: AsyncEngine,
    *,
    execution_id: str,
    title: str = "task",
    status: WorkflowTaskStatus = WorkflowTaskStatus.completed,
    error_kind: TaskErrorKind | None = None,
    error_message: str | None = None,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a WorkflowTask and return its id."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title=title,
            status=status,
            error_kind=error_kind,
            error_message=error_message,
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task.id


async def _seed_approval(
    eng: AsyncEngine,
    *,
    execution_id: str,
    approver: str | None,
    status: ApprovalStatus = ApprovalStatus.pending,
    created_at: datetime | None = None,
    decided_at: datetime | None = None,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert an Approval with explicit timing fields and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=execution_id,
            title="Approve me",
            status=status,
            approver=approver,
            created_at=created_at or datetime.now(UTC),
            decided_at=decided_at,
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


def _samples(body: str, metric: str) -> dict[frozenset[tuple[str, str]], float]:
    """Parse an exposition body into ``{label set: value}`` for one metric name.

    Keys are frozen sets of label pairs rather than the raw label text because
    ``prometheus_client`` emits labels in alphabetical order, not declaration
    order — asserting on the rendered string would couple every test to that.

    Args:
        body: The full Prometheus exposition text.
        metric: The fully qualified metric name to extract.

    Returns:
        A mapping from each sample's label set to its value.
    """
    out: dict[frozenset[tuple[str, str]], float] = {}
    for line in body.splitlines():
        if line.startswith("#") or not line.startswith(f"{metric}{{"):
            continue
        labels, _, value = line.partition(" ")
        pairs = labels[len(metric) :].strip("{}").split(",")
        key = frozenset(
            (name, text.strip('"'))
            for name, _, text in (pair.partition("=") for pair in pairs)
        )
        out[key] = float(value)
    return out


def _labels(**pairs: str) -> frozenset[tuple[str, str]]:
    """Build the label-set key matching a sample, tenant label included."""
    return frozenset({("tenant", DEFAULT_TEST_TENANT_ID), *pairs.items()})


# --------------------------------------------------------------------------
# Prometheus exposition
# --------------------------------------------------------------------------


async def test_metrics_exposes_pending_approvals_and_active_runs(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Onboarding")
    execution_id = await _seed_execution(eng, workflow_id=workflow_id)
    await _seed_approval(eng, execution_id=execution_id, approver="alice")

    res = await client.get("/api/v1/metrics", headers={"X-User-Id": "owner"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.text
    assert _samples(body, "a2flow_approvals_pending") == {_labels(): 1.0}
    assert _samples(body, "a2flow_workflow_executions_active") == {_labels(): 1.0}


async def test_metrics_counts_stalled_approvals_against_the_threshold(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    execution_id = await _seed_execution(eng, workflow_id=None)
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="alice",
        created_at=datetime.now(UTC) - timedelta(hours=30),
    )
    await _seed_approval(eng, execution_id=execution_id, approver="bob")

    res = await client.get("/api/v1/metrics", headers={"X-User-Id": "owner"})
    body = res.text

    stalled = _samples(body, "a2flow_approvals_pending_over_threshold")
    assert stalled == {_labels(threshold="24h"): 1.0}
    oldest = _samples(body, "a2flow_approval_pending_age_seconds_max")
    assert next(iter(oldest.values())) > 29 * 3600


async def test_metrics_threshold_is_configurable(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    execution_id = await _seed_execution(eng, workflow_id=None)
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="alice",
        created_at=datetime.now(UTC) - timedelta(hours=30),
    )

    res = await client.get(
        "/api/v1/metrics?thresholdHours=48", headers={"X-User-Id": "owner"}
    )

    assert _samples(res.text, "a2flow_approvals_pending_over_threshold") == {
        _labels(threshold="48h"): 0.0
    }


async def test_metrics_reports_decisions_and_failures(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Invoices")
    now = datetime.now(UTC)
    # Clamped to today's UTC midnight (METRICS_TIMEZONE defaults to UTC, see
    # MetricsService._day_start): a plain `now - timedelta(...)` would fall on
    # the previous day, and drop out of the "today" gauges below, whenever the
    # suite runs within a couple of hours of UTC midnight.
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    execution_id = await _seed_execution(
        eng,
        workflow_id=workflow_id,
        status=WorkflowExecutionStatus.failed,
        created_at=max(today_start, now - timedelta(hours=2)),
        finished_at=max(today_start, now - timedelta(hours=1)),
    )
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="alice",
        status=ApprovalStatus.approved,
        decided_at=max(today_start, now - timedelta(minutes=30)),
    )
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="bob",
        status=ApprovalStatus.returned,
        decided_at=max(today_start, now - timedelta(minutes=20)),
    )
    await _seed_task(
        eng,
        execution_id=execution_id,
        status=WorkflowTaskStatus.failed,
        error_kind=TaskErrorKind.api_error,
    )

    res = await client.get("/api/v1/metrics", headers={"X-User-Id": "owner"})
    body = res.text

    decided = _samples(body, "a2flow_approvals_decided_today")
    assert decided[_labels(decision="approved")] == 1.0
    assert decided[_labels(decision="returned")] == 1.0
    # Emitted as an explicit zero so a dashboard's approval-rate denominator
    # never has a missing series.
    assert decided[_labels(decision="rejected")] == 0.0

    assert _samples(body, "a2flow_workflow_executions_failed_recently") == {
        _labels(window="24h"): 1.0
    }
    assert _samples(body, "a2flow_workflow_tasks_failed_recently") == {
        _labels(window="24h", error_kind="api_error"): 1.0
    }
    assert _samples(body, "a2flow_workflow_executions_finished_today") == {
        _labels(status="failed"): 1.0
    }


async def test_metrics_reports_volume_and_lead_time_per_workflow(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Payroll")
    now = datetime.now(UTC)
    await _seed_execution(
        eng,
        workflow_id=workflow_id,
        name="run-a",
        status=WorkflowExecutionStatus.completed,
        created_at=now - timedelta(hours=3),
        finished_at=now - timedelta(hours=2),
    )

    res = await client.get("/api/v1/metrics", headers={"X-User-Id": "owner"})
    body = res.text

    assert _samples(body, "a2flow_workflow_executions_started_recently") == {
        _labels(window="24h", workflow="Payroll"): 1.0
    }
    lead = _samples(body, "a2flow_workflow_execution_lead_time_seconds_avg")
    assert lead[_labels(window="24h", workflow="Payroll")] == 3600.0


async def test_metrics_does_not_leak_across_tenants(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    mine = await _seed_execution(eng, workflow_id=None, name="mine")
    await _seed_approval(eng, execution_id=mine, approver="alice")
    theirs = await _seed_execution(
        eng, workflow_id=None, name="theirs", tenant_id=OTHER_TENANT_ID
    )
    await _seed_approval(
        eng, execution_id=theirs, approver="alice", tenant_id=OTHER_TENANT_ID
    )

    res = await client.get("/api/v1/metrics", headers={"X-User-Id": "owner"})

    # One approval and one run, not two: the other tenant's rows are invisible.
    assert _samples(res.text, "a2flow_approvals_pending") == {_labels(): 1.0}
    assert _samples(res.text, "a2flow_workflow_executions_active") == {_labels(): 1.0}


# --------------------------------------------------------------------------
# Aggregate sub-resources
# --------------------------------------------------------------------------


async def test_by_workflow_groups_runs_and_averages_lead_time(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Payroll")
    now = datetime.now(UTC)
    await _seed_execution(
        eng,
        workflow_id=workflow_id,
        name="run-a",
        status=WorkflowExecutionStatus.completed,
        created_at=now - timedelta(hours=5),
        finished_at=now - timedelta(hours=4),
    )
    await _seed_execution(
        eng,
        workflow_id=workflow_id,
        name="run-b",
        status=WorkflowExecutionStatus.failed,
        created_at=now - timedelta(hours=5),
        finished_at=now - timedelta(hours=2),
    )
    await _seed_execution(eng, workflow_id=workflow_id, name="run-c")

    res = await client.get(
        "/api/v1/workflow-executions/by-workflow", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)

    assert len(data) == 1
    entry = data[0]
    assert entry["workflowId"] == workflow_id
    assert entry["workflowName"] == "Payroll"
    assert entry["total"] == 3
    assert entry["running"] == 1
    assert entry["completed"] == 1
    assert entry["failed"] == 1
    # Only the two finished runs count: (3600 + 10800) / 2.
    assert entry["avgLeadTimeSeconds"] == 7200.0


async def test_by_workflow_keeps_runs_whose_workflow_was_deleted(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    await _seed_execution(eng, workflow_id=None, name="orphan-run")

    res = await client.get(
        "/api/v1/workflow-executions/by-workflow", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)

    assert data[0]["workflowId"] is None
    # Falls back to the run's own name snapshot.
    assert data[0]["workflowName"] == "orphan-run"


async def test_lead_time_trend_fills_days_with_no_completions(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    now = datetime.now(UTC)
    await _seed_execution(
        eng,
        workflow_id=None,
        status=WorkflowExecutionStatus.completed,
        created_at=now - timedelta(hours=2),
        finished_at=now - timedelta(hours=1),
    )

    since = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    res = await client.get(
        f"/api/v1/workflow-executions/lead-time-trend?since={since}",
        headers={"X-User-Id": "owner"},
    )
    data = assert_ok(res)

    assert len(data) == 3
    assert [b["bucketStart"] for b in data] == sorted(b["bucketStart"] for b in data)
    assert sum(b["count"] for b in data) == 1
    # The empty days are present but carry no average to plot.
    assert [b["avgLeadTimeSeconds"] for b in data].count(None) == 2


async def test_failures_lists_runs_with_their_failed_tasks(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Invoices")
    execution_id = await _seed_execution(
        eng,
        workflow_id=workflow_id,
        name="run-a",
        status=WorkflowExecutionStatus.failed,
    )
    await _seed_task(
        eng,
        execution_id=execution_id,
        title="Call the billing API",
        status=WorkflowTaskStatus.failed,
        error_kind=TaskErrorKind.api_error,
        error_message="billing API returned 503",
    )
    await _seed_task(eng, execution_id=execution_id, title="Summarize")

    res = await client.get(
        "/api/v1/workflow-executions/failures", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)

    assert len(data) == 1
    assert data[0]["executionId"] == execution_id
    assert data[0]["workflowName"] == "Invoices"
    # Only the failed task, not the completed one.
    assert len(data[0]["failedTasks"]) == 1
    failure = data[0]["failedTasks"][0]
    assert failure["title"] == "Call the billing API"
    assert failure["errorKind"] == "api_error"
    assert failure["errorMessage"] == "billing API returned 503"


async def test_approval_backlog_by_approver_ranks_the_longest_wait_first(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    execution_id = await _seed_execution(eng, workflow_id=None)
    now = datetime.now(UTC)
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="alice",
        created_at=now - timedelta(hours=2),
    )
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="bob",
        created_at=now - timedelta(hours=40),
    )
    await _seed_approval(
        eng,
        execution_id=execution_id,
        approver="bob",
        created_at=now - timedelta(hours=1),
    )

    res = await client.get(
        "/api/v1/approvals/by-approver", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)

    assert [e["groupId"] for e in data] == ["bob", "alice"]
    assert data[0]["pending"] == 2
    assert data[0]["overThreshold"] == 1
    assert data[0]["maxWaitSeconds"] > 39 * 3600
    # Approver names are left for the client to resolve.
    assert data[0]["groupLabel"] is None


async def test_approval_backlog_by_workflow_labels_the_workflow(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    workflow_id = await _seed_workflow(eng, name="Onboarding")
    execution_id = await _seed_execution(eng, workflow_id=workflow_id)
    await _seed_approval(eng, execution_id=execution_id, approver="alice")

    res = await client.get(
        "/api/v1/approvals/by-workflow", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)

    assert data[0]["groupId"] == workflow_id
    assert data[0]["groupLabel"] == "Onboarding"
    assert data[0]["pending"] == 1


async def test_aggregate_endpoints_do_not_leak_across_tenants(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = metrics_env
    theirs = await _seed_execution(
        eng, workflow_id=None, name="theirs", tenant_id=OTHER_TENANT_ID
    )
    await _seed_approval(
        eng, execution_id=theirs, approver="alice", tenant_id=OTHER_TENANT_ID
    )
    await _seed_task(
        eng,
        execution_id=theirs,
        status=WorkflowTaskStatus.failed,
        error_kind=TaskErrorKind.timeout,
        tenant_id=OTHER_TENANT_ID,
    )

    headers = {"X-User-Id": "owner"}
    assert (
        assert_ok(await client.get("/api/v1/approvals/by-approver", headers=headers))
        == []
    )
    assert (
        assert_ok(
            await client.get("/api/v1/workflow-executions/by-workflow", headers=headers)
        )
        == []
    )
    assert (
        assert_ok(
            await client.get("/api/v1/workflow-executions/failures", headers=headers)
        )
        == []
    )


async def test_metrics_window_must_be_ordered(
    metrics_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = metrics_env

    res = await client.get(
        "/api/v1/workflow-executions/by-workflow"
        "?since=2026-01-02T00:00:00Z&until=2026-01-01T00:00:00Z",
        headers={"X-User-Id": "owner"},
    )

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_QUERY"
