"""Tests for the WorkflowTask agent tools in ``infrastructure.workflow_task_tools``.

The tools open their own ``AsyncSession`` on ``infrastructure.database.engine``;
each test monkeypatches that engine to an isolated in-memory SQLite database and
drives the tools with a lightweight fake ToolContext exposing only ``session.id``
and ``user_id`` (the attributes the tools read).
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.workflow_task_tools import (
    _resolve_ws_id,
    create_workflow_task,
    delete_workflow_task,
    get_workflow_task,
    list_workflow_tasks,
    register_workflow_tasks,
    update_workflow_task,
)
from models.workflow_session import WorkflowSession
from repositories import SqlWorkflowSessionRepository


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine and point the tools' module-level engine at it."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_session(
    eng: AsyncEngine, *, session_id: str = "sess-abc", user_id: str = "owner"
) -> str:
    """Insert a WorkflowSession with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        ws = WorkflowSession(
            session_id=session_id,
            workflow_name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            user_id=user_id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.id


def _ctx(session_id: str = "sess-abc", user_id: str = "tester") -> Any:
    """Build a fake ToolContext exposing ``session.id`` and ``user_id``."""
    return SimpleNamespace(session=SimpleNamespace(id=session_id), user_id=user_id)


async def test_register_workflow_tasks_creates_dag(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await register_workflow_tasks(
        [
            {"key": "t0", "title": "First"},
            {"key": "t1", "title": "Second", "depends_on": ["t0"]},
            {"key": "t2", "title": "Third", "depends_on": ["t0", "t1"]},
        ],
        _ctx(),
    )
    assert "error" not in result
    created = result["created"]
    assert [c["key"] for c in created] == ["t0", "t1", "t2"]
    ids = {c["key"]: c["id"] for c in created}

    listed = await list_workflow_tasks(_ctx())
    tasks = {t["title"]: t for t in listed["tasks"]}
    assert tasks["Second"]["depends_on_ids"] == [ids["t0"]]
    assert sorted(tasks["Third"]["depends_on_ids"]) == sorted([ids["t0"], ids["t1"]])
    # Positions follow dependency order when not declared.
    assert [t["title"] for t in listed["tasks"]] == ["First", "Second", "Third"]


async def test_register_rejects_unknown_dependency(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await register_workflow_tasks(
        [{"key": "a", "title": "A", "depends_on": ["missing"]}], _ctx()
    )
    assert "error" in result
    listed = await list_workflow_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_rejects_duplicate_key(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await register_workflow_tasks(
        [{"key": "a", "title": "A"}, {"key": "a", "title": "B"}], _ctx()
    )
    assert "error" in result


async def test_register_rejects_cycle(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await register_workflow_tasks(
        [
            {"key": "a", "title": "A", "depends_on": ["b"]},
            {"key": "b", "title": "B", "depends_on": ["a"]},
        ],
        _ctx(),
    )
    assert "error" in result
    assert "cycle" in result["error"]


async def test_register_rejects_missing_title(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await register_workflow_tasks([{"key": "a"}], _ctx())
    assert "error" in result


async def test_register_without_session_errors(engine: AsyncEngine) -> None:
    result = await register_workflow_tasks(
        [{"key": "a", "title": "A"}], _ctx("unknown-session")
    )
    assert "error" in result


async def test_create_workflow_task(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await create_workflow_task("Solo", _ctx())
    assert result["title"] == "Solo"
    assert result["status"] == "pending"


async def test_create_with_invalid_status(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await create_workflow_task("X", _ctx(), status="bogus")
    assert "error" in result


async def test_list_isolates_sessions(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    await create_workflow_task("In A", _ctx("sess-a"))
    await create_workflow_task("In B", _ctx("sess-b"))
    listed_a = await list_workflow_tasks(_ctx("sess-a"))
    assert [t["title"] for t in listed_a["tasks"]] == ["In A"]


async def test_get_workflow_task_cross_session_guard(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    created = await create_workflow_task("Owned by A", _ctx("sess-a"))
    task_id = created["id"]

    blocked = await get_workflow_task(task_id, _ctx("sess-b"))
    assert "error" in blocked
    allowed = await get_workflow_task(task_id, _ctx("sess-a"))
    assert allowed["id"] == task_id


async def test_update_status(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    created = await create_workflow_task("Task", _ctx())
    updated = await update_workflow_task(created["id"], _ctx(), status="in_progress")
    assert updated["status"] == "in_progress"


async def test_update_invalid_status(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    created = await create_workflow_task("Task", _ctx())
    result = await update_workflow_task(created["id"], _ctx(), status="nope")
    assert "error" in result


async def test_update_dependencies(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    a = await create_workflow_task("A", _ctx())
    b = await create_workflow_task("B", _ctx())
    updated = await update_workflow_task(b["id"], _ctx(), depends_on_ids=[a["id"]])
    assert updated["depends_on_ids"] == [a["id"]]


async def test_update_dependency_cycle_rejected(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    a = await create_workflow_task("A", _ctx())
    b = await create_workflow_task("B", _ctx(), depends_on_ids=[a["id"]])
    result = await update_workflow_task(a["id"], _ctx(), depends_on_ids=[b["id"]])
    assert "error" in result


async def test_update_preserves_unset_fields(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    created = await create_workflow_task("Original", _ctx(), description="desc")
    updated = await update_workflow_task(created["id"], _ctx(), status="completed")
    assert updated["title"] == "Original"
    assert updated["description"] == "desc"
    assert updated["status"] == "completed"


async def test_delete_workflow_task(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    created = await create_workflow_task("Temp", _ctx())
    result = await delete_workflow_task(created["id"], _ctx())
    assert result == {"deleted": created["id"]}
    listed = await list_workflow_tasks(_ctx())
    assert listed["tasks"] == []


async def test_delete_cross_session_guard(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    created = await create_workflow_task("A", _ctx("sess-a"))
    result = await delete_workflow_task(created["id"], _ctx("sess-b"))
    assert "error" in result


async def test_resolve_ws_id(engine: AsyncEngine) -> None:
    ws_id = await _seed_session(engine, session_id="sess-x")
    async with AsyncSession(engine) as db:
        repo = SqlWorkflowSessionRepository(db)
        assert await _resolve_ws_id(_ctx("sess-x"), repo) == ws_id
        assert await _resolve_ws_id(_ctx("absent"), repo) is None


async def test_get_by_session_id(engine: AsyncEngine) -> None:
    ws_id = await _seed_session(engine, session_id="sess-find")
    async with AsyncSession(engine) as db:
        repo = SqlWorkflowSessionRepository(db)
        found = await repo.get_by_session_id("sess-find")
        assert found is not None
        assert found.id == ws_id
        assert await repo.get_by_session_id("absent") is None
