"""Tests for assigning a run's tasks to its ADK sessions, and what that assignment gates.

:func:`services.execution_branching.plan_assignments` is pure, so its rules are
tested on hand-built rows. The rest runs against a throwaway database: the
compare-and-set claim, a branch session resolving to its run, and the two
places a session's reach is enforced outside ``update_workflow_task`` -- the
MCP policies' view of what is in progress, and ``request_approval``.
"""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.approval_tools import request_approval
from infrastructure.mcp_policies import _in_progress_tasks
from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories.mcp_server import SqlMCPServerRepository
from repositories.tenant_bootstrap import resolve_workflow_execution_tenant
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from repositories.workflow_task import SqlWorkflowTaskRepository
from services.execution_branching import Assignment, plan_assignments
from tests._engine import make_test_engine
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    seed_branch_session,
    seed_tenant,
    seed_users,
    seed_workflow_task,
)

MAIN = "main"
BRANCH = "branch"

pending = WorkflowTaskStatus.pending
completed = WorkflowTaskStatus.completed


def _task(
    task_id: str,
    status: WorkflowTaskStatus = pending,
    *,
    deps: Sequence[str] = (),
    session_id: str | None = None,
) -> WorkflowTaskRead:
    """Build a task row for the pure planner."""
    return WorkflowTaskRead(
        id=task_id,
        workflow_execution_id="run",
        title=task_id,
        status=status,
        session_id=session_id,
        depends_on_ids=list(deps),
        created_by="owner",
        updated_by="owner",
    )


def _session(
    session_id: str, status: ExecutionSessionStatus = ExecutionSessionStatus.idle
) -> ExecutionSession:
    """Build a session row for the pure planner."""
    return ExecutionSession(
        id=session_id,
        workflow_execution_id="run",
        parent_id=None if session_id == MAIN else MAIN,
        status=status,
        tenant_id=DEFAULT_TEST_TENANT_ID,
        created_by="owner",
        updated_by="owner",
    )


def _plan(
    tasks: Sequence[WorkflowTaskRead],
    sessions: Sequence[ExecutionSession] = (),
    *,
    max_sessions: int = 1,
) -> list[Assignment]:
    """Plan with the main session plus ``sessions``; serial (no forking) by default."""
    return plan_assignments(
        tasks,
        [_session(MAIN), *sessions],
        main_session_id=MAIN,
        max_sessions=max_sessions,
    )


# ---------- forking ----------


def test_a_branch_point_forks_the_extra_branches() -> None:
    tasks = [
        _task("a", completed, session_id=MAIN),
        _task("b", deps=["a"]),
        _task("c", deps=["a"]),
        _task("d", deps=["a"]),
    ]
    assert _plan(tasks, max_sessions=4) == [
        Assignment("b", MAIN),
        Assignment("c", None, fork_from=MAIN),
        Assignment("d", None, fork_from=MAIN),
    ]


def test_independent_roots_run_side_by_side() -> None:
    assert _plan([_task("a"), _task("b")], max_sessions=4) == [
        Assignment("a", MAIN),
        Assignment("b", None, fork_from=MAIN),
    ]


def test_at_the_cap_a_branch_queues_on_its_target() -> None:
    tasks = [
        _task("a", completed, session_id=MAIN),
        _task("b", deps=["a"]),
        _task("c", deps=["a"]),
    ]
    # The main session and one live branch already fill a cap of two.
    assert _plan(tasks, [_session(BRANCH)], max_sessions=2) == [
        Assignment("b", MAIN),
        Assignment("c", MAIN),
    ]


def test_a_branch_forks_from_itself_when_it_branches_again() -> None:
    tasks = [
        _task("c", completed, session_id=BRANCH),
        _task("d", deps=["c"]),
        _task("e", deps=["c"]),
    ]
    assert _plan(tasks, [_session(BRANCH)], max_sessions=4) == [
        Assignment("d", BRANCH),
        Assignment("e", None, fork_from=BRANCH),
    ]


def test_a_join_never_forks() -> None:
    tasks = [
        _task("a", completed, session_id=MAIN),
        _task("busy", WorkflowTaskStatus.in_progress, session_id=MAIN),
        _task("b", completed, session_id=BRANCH),
        _task("join", deps=["a", "b"]),
    ]
    done = _session(BRANCH, ExecutionSessionStatus.done)
    assert _plan(tasks, [done], max_sessions=4) == [Assignment("join", MAIN)]


# ---------- plan_assignments ----------


def test_root_tasks_go_to_the_main_session() -> None:
    assert _plan([_task("a"), _task("b")]) == [
        Assignment("a", MAIN),
        Assignment("b", MAIN),
    ]


def test_a_task_waits_for_every_dependency_to_complete() -> None:
    tasks = [
        _task("a", completed, session_id=MAIN),
        _task("b"),
        _task("c", deps=["a", "b"]),
    ]
    assert _plan(tasks) == [Assignment("b", MAIN)]


def test_assigned_and_started_tasks_are_left_alone() -> None:
    tasks = [
        _task("a", session_id=MAIN),
        _task("b", WorkflowTaskStatus.in_progress, session_id=MAIN),
    ]
    assert _plan(tasks) == []


def test_a_task_follows_its_live_branch() -> None:
    tasks = [_task("a", completed, session_id=BRANCH), _task("b", deps=["a"])]
    assert _plan(tasks, [_session(BRANCH)]) == [Assignment("b", BRANCH)]


def test_a_task_after_a_finished_branch_returns_to_main() -> None:
    tasks = [_task("a", completed, session_id=BRANCH), _task("b", deps=["a"])]
    done = _session(BRANCH, ExecutionSessionStatus.done)
    assert _plan(tasks, [done]) == [Assignment("b", MAIN)]


def test_a_join_waits_until_its_branches_finish() -> None:
    tasks = [
        _task("a", completed, session_id=MAIN),
        _task("b", completed, session_id=BRANCH),
        _task("join", deps=["a", "b"]),
    ]
    assert _plan(tasks, [_session(BRANCH)]) == []
    done = _session(BRANCH, ExecutionSessionStatus.done)
    assert _plan(tasks, [done]) == [Assignment("join", MAIN)]


def test_a_dependency_with_no_session_counts_as_the_main_sessions() -> None:
    tasks = [_task("a", completed), _task("b", deps=["a"])]
    assert _plan(tasks) == [Assignment("b", MAIN)]


# ---------- against a database ----------


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


async def _seed_run(eng: AsyncEngine) -> str:
    """Insert a run whose main session is ``main`` plus a live ``branch`` session."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=MAIN,
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
        # Read before the commit expires it: reloading would need a greenlet.
        execution_id = execution.id
        db.add(execution)
        await db.commit()
    await seed_branch_session(eng, execution_id, MAIN)
    await seed_branch_session(eng, execution_id, BRANCH, parent_id=MAIN)
    return execution_id


def _ctx(session_id: str) -> Any:
    """Build a fake ToolContext for the initiator, called from ``session_id``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id="owner", state=None
    )


async def test_a_branch_session_resolves_to_its_run(engine: AsyncEngine) -> None:
    execution_id = await _seed_run(engine)
    async with AsyncSession(engine) as db:
        assert await resolve_workflow_execution_tenant(db, BRANCH) == (
            execution_id,
            DEFAULT_TEST_TENANT_ID,
        )
        assert await resolve_workflow_execution_tenant(db, "unknown") is None


async def test_concurrent_claims_have_exactly_one_winner(engine: AsyncEngine) -> None:
    execution_id = await _seed_run(engine)
    task_id = await seed_workflow_task(engine, execution_id)

    async def _claim(session_id: str) -> bool:
        async with AsyncSession(engine) as db:
            executions = SqlWorkflowExecutionRepository(
                db, tenant_id=DEFAULT_TEST_TENANT_ID
            )
            repo = SqlWorkflowTaskRepository(
                db,
                executions,
                SqlMCPServerRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID),
                tenant_id=DEFAULT_TEST_TENANT_ID,
            )
            return await repo.claim(task_id, session_id, user_id="owner")

    results = await asyncio.gather(_claim(MAIN), _claim(BRANCH))
    assert sorted(results) == [False, True]


async def test_mcp_policies_see_only_the_calling_sessions_tasks(
    engine: AsyncEngine,
) -> None:
    """Two branches in progress at once must not share tools or certificates."""
    execution_id = await _seed_run(engine)
    in_progress = WorkflowTaskStatus.in_progress
    mine = await seed_workflow_task(
        engine, execution_id, status=in_progress, session_id=BRANCH
    )
    main_task = await seed_workflow_task(
        engine, execution_id, status=in_progress, session_id=MAIN
    )
    unassigned = await seed_workflow_task(engine, execution_id, status=in_progress)

    async with AsyncSession(engine) as db:
        branch_view = await _in_progress_tasks(
            db, execution_id, DEFAULT_TEST_TENANT_ID, BRANCH
        )
        main_view = await _in_progress_tasks(
            db, execution_id, DEFAULT_TEST_TENANT_ID, MAIN
        )
    assert [t.id for t in branch_view] == [mine]
    assert sorted(t.id for t in main_view) == sorted([main_task, unassigned])


async def test_a_branch_cannot_gate_another_branchs_task(engine: AsyncEngine) -> None:
    execution_id = await _seed_run(engine)
    main_task = await seed_workflow_task(engine, execution_id, session_id=MAIN)
    branch_task = await seed_workflow_task(engine, execution_id, session_id=BRANCH)
    downstream = await seed_workflow_task(
        engine, execution_id, depends_on_ids=[branch_task]
    )

    refused = await request_approval(
        title="Go?",
        tool_context=_ctx(BRANCH),
        workflow_task_id=main_task,
        approver="bob",
    )
    assert "outside the part of the run" in refused["error"]
    for own in (branch_task, downstream):
        accepted = await request_approval(
            title="Go?", tool_context=_ctx(BRANCH), workflow_task_id=own, approver="bob"
        )
        assert accepted.get("status") == "pending", accepted
