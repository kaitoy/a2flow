"""Tests for the background plan-generation job in ``services.workflow_planning``.

The job runs outside FastAPI's request scope: it opens database sessions of its
own on ``infrastructure.database.engine``, so each test monkeypatches that
engine to an isolated in-memory SQLite database and drives the job with fake
singletons (agent registry, session service, skill store) plus a monkeypatched
summarizer — the LLM never runs.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from google.adk.sessions import InMemorySessionService
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.notification import Notification, NotificationType
from models.planning_session import PlanningSession
from models.workflow import Workflow, WorkflowStatus
from models.workflow_task_template import WorkflowTaskTemplate
from services.workflow_planning import generate_workflow_plan
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

_SHA = "a" * 40


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine and point the job's module-level engine at it."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng, ids=("owner",))
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed(eng: AsyncEngine) -> tuple[str, str]:
    """Insert a skill + generating workflow + planning session; return (wf_id, session_id)."""
    async with AsyncSession(eng, expire_on_commit=False) as db:
        skill = AgentSkill(
            name="skill-a",
            repo_url="https://example.com/repo",
            repo_path="",
            commit_sha=_SHA,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(skill)
        await db.commit()
        workflow = Workflow(
            name="wf-a",
            agent_skill_id=skill.id,
            status=WorkflowStatus.generating,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(workflow)
        await db.commit()
        ps = PlanningSession(
            session_id="plan-sess-1",
            workflow_id=workflow.id,
            agent_skill_id=skill.id,
            agent_skill_commit_sha=_SHA,
            user_id="owner",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(ps)
        await db.commit()
        return workflow.id, ps.session_id


async def _add_template(eng: AsyncEngine, workflow_id: str) -> None:
    async with AsyncSession(eng) as db:
        db.add(
            WorkflowTaskTemplate(
                workflow_id=workflow_id,
                title="Generated step",
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="owner",
                updated_by="owner",
            )
        )
        await db.commit()


def _fakes(
    tmp_path: Path, *, run_registers: bool = False, eng: AsyncEngine | None = None
) -> tuple[MagicMock, InMemorySessionService, MagicMock]:
    """Build the (registry, session_service, skills_store) fakes for the job.

    When ``run_registers`` is set the fake agent run inserts one template into
    the workflow's plan, standing in for the ``register_planning_tasks`` call a
    real initial-planning run makes.
    """
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir(exist_ok=True)

    captured: dict[str, Any] = {}

    async def _run(input_data: Any) -> AsyncGenerator[Any, None]:
        captured["input"] = input_data
        if run_registers:
            assert eng is not None
            async with AsyncSession(eng) as db:
                ps = (
                    await db.exec(
                        select(PlanningSession).where(
                            PlanningSession.session_id == input_data.thread_id
                        )
                    )
                ).first()
                assert ps is not None
                db.add(
                    WorkflowTaskTemplate(
                        workflow_id=ps.workflow_id,
                        title="Generated step",
                        tenant_id=DEFAULT_TEST_TENANT_ID,
                        created_by="owner",
                        updated_by="owner",
                    )
                )
                await db.commit()
        return
        yield

    agent = MagicMock()
    agent.run = _run
    registry = MagicMock()
    registry.get.return_value = agent
    registry.captured = captured

    store = MagicMock()
    store.skill_dir = MagicMock(return_value=skill_dir)

    return registry, InMemorySessionService(), store  # type: ignore[no-untyped-call]


async def _workflow_row(eng: AsyncEngine, workflow_id: str) -> Workflow:
    async with AsyncSession(eng) as db:
        workflow = await db.get(Workflow, workflow_id)
        assert workflow is not None
        return workflow


async def test_generation_job_success_sets_draft_and_notifies(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from infrastructure.agent import AgentKind

    wf_id, _session_id = await _seed(engine)
    registry, session_service, store = _fakes(tmp_path, run_registers=True, eng=engine)

    async def _fake_summarize(transcript: str, **_: Any) -> str:
        return "A summary of the plan"

    monkeypatch.setattr(
        "services.workflow_planning.summarize_planning_transcript", _fake_summarize
    )

    await generate_workflow_plan(
        wf_id,
        "Build me a report",
        user_id="owner",
        registry=registry,
        session_service=session_service,
        skills_store=store,
        app_name="A2Flow",
    )

    workflow = await _workflow_row(engine, wf_id)
    assert workflow.status is WorkflowStatus.draft
    assert workflow.generation_error is None
    assert workflow.description == "A summary of the plan"

    # The run went through the initial-planning agent with the prompt as the
    # user message, keyed by the session owner.
    assert registry.get.call_args.kwargs["kind"] is AgentKind.initial_planning
    input_data = registry.captured["input"]
    assert input_data.thread_id == "plan-sess-1"
    assert input_data.messages[0].content == "Build me a report"
    assert input_data.forwarded_props["userId"] == "owner"

    async with AsyncSession(engine) as db:
        notifications = (await db.exec(select(Notification))).all()
    assert len(notifications) == 1
    assert notifications[0].type is NotificationType.workflow_draft_ready
    assert notifications[0].user_id == "owner"
    assert notifications[0].workflow_id == wf_id


async def test_generation_job_without_templates_fails_the_workflow(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    wf_id, _session_id = await _seed(engine)
    registry, session_service, store = _fakes(tmp_path)

    await generate_workflow_plan(
        wf_id,
        "Build me a report",
        user_id="owner",
        registry=registry,
        session_service=session_service,
        skills_store=store,
        app_name="A2Flow",
    )

    workflow = await _workflow_row(engine, wf_id)
    assert workflow.status is WorkflowStatus.failed
    assert "no task templates" in (workflow.generation_error or "")


async def test_generation_job_failure_lands_on_the_row(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """Any crash must settle the workflow as failed — nothing else clears 'generating'."""
    wf_id, _session_id = await _seed(engine)
    registry, session_service, store = _fakes(tmp_path)
    store.skill_dir = MagicMock(return_value=tmp_path / "missing-revision")

    await generate_workflow_plan(
        wf_id,
        "Build me a report",
        user_id="owner",
        registry=registry,
        session_service=session_service,
        skills_store=store,
        app_name="A2Flow",
    )

    workflow = await _workflow_row(engine, wf_id)
    assert workflow.status is WorkflowStatus.failed
    assert workflow.generation_error


async def test_generation_job_summarizer_failure_falls_back(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A summarizer hiccup must not fail a generation that produced a plan."""
    wf_id, _session_id = await _seed(engine)
    registry, session_service, store = _fakes(tmp_path, run_registers=True, eng=engine)

    async def _boom(transcript: str, **_: Any) -> str:
        raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "services.workflow_planning.summarize_planning_transcript", _boom
    )

    await generate_workflow_plan(
        wf_id,
        "Build me a report",
        user_id="owner",
        registry=registry,
        session_service=session_service,
        skills_store=store,
        app_name="A2Flow",
    )

    workflow = await _workflow_row(engine, wf_id)
    assert workflow.status is WorkflowStatus.draft
