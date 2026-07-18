"""Tests for the planning agent tools in ``infrastructure.planning_task_tools``.

The tools open their own ``AsyncSession`` on ``infrastructure.database.engine``;
each test monkeypatches that engine to an isolated in-memory SQLite database and
drives the tools with a lightweight fake ToolContext exposing only ``session.id``
and ``user_id`` (the attributes the tools read). Unlike the session-task tools,
these resolve a PlanningSession and edit the linked workflow's task templates.
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

from infrastructure.planning_task_tools import (
    create_planning_task,
    delete_planning_task,
    get_planning_task,
    list_planning_tasks,
    register_planning_tasks,
    update_planning_task,
)
from models.agent_skill import AgentSkill
from models.planning_session import PlanningSession
from models.workflow import Workflow
from repositories.tenant_bootstrap import resolve_planning_session_tenant
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


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
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_planning_session(
    eng: AsyncEngine, *, session_id: str = "plan-abc", user_id: str = "owner"
) -> str:
    """Insert a skill + workflow + PlanningSession chain; return the workflow PK."""
    async with AsyncSession(eng) as db:
        skill = AgentSkill(
            name=f"skill-{session_id}",
            repo_url="https://example.com/repo",
            repo_path="",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)

        skill_id = skill.id
        workflow = Workflow(
            name=f"wf-{session_id}",
            agent_skill_id=skill_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

        ps = PlanningSession(
            session_id=session_id,
            workflow_id=workflow_id,
            agent_skill_id=skill_id,
            agent_skill_commit_sha="a" * 40,
            user_id=user_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(ps)
        await db.commit()
        return workflow_id


def _ctx(session_id: str = "plan-abc", user_id: str = "tester") -> Any:
    """Build a fake ToolContext exposing ``session.id`` and ``user_id``."""
    return SimpleNamespace(session=SimpleNamespace(id=session_id), user_id=user_id)


# ---------- register ----------


async def test_register_planning_tasks_creates_dag(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
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

    listed = await list_planning_tasks(_ctx())
    tasks = {t["title"]: t for t in listed["tasks"]}
    assert tasks["Second"]["depends_on_ids"] == [ids["t0"]]
    assert sorted(tasks["Third"]["depends_on_ids"]) == sorted([ids["t0"], ids["t1"]])
    # Positions follow dependency order when not declared, and templates have
    # no status — the lifecycle belongs to a run.
    assert [t["title"] for t in listed["tasks"]] == ["First", "Second", "Third"]
    assert all("status" not in t for t in listed["tasks"])


async def test_register_rejects_unknown_dependency(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
        [{"key": "a", "title": "A", "depends_on": ["missing"]}], _ctx()
    )
    assert "error" in result
    listed = await list_planning_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_rejects_duplicate_key(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
        [{"key": "a", "title": "A"}, {"key": "a", "title": "B"}], _ctx()
    )
    assert "error" in result


async def test_register_rejects_cycle(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
        [
            {"key": "a", "title": "A", "depends_on": ["b"]},
            {"key": "b", "title": "B", "depends_on": ["a"]},
        ],
        _ctx(),
    )
    assert "error" in result
    assert "cycle" in result["error"]


async def test_register_rejects_missing_title(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks([{"key": "a"}], _ctx())
    assert "error" in result


async def test_register_without_session_errors(engine: AsyncEngine) -> None:
    result = await register_planning_tasks(
        [{"key": "a", "title": "A"}], _ctx("unknown-session")
    )
    assert "error" in result


# ---------- single-template CRUD ----------


async def test_create_planning_task(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await create_planning_task("Solo", _ctx())
    assert result["title"] == "Solo"
    assert "status" not in result


async def test_list_isolates_workflows(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine, session_id="plan-a")
    await _seed_planning_session(engine, session_id="plan-b")
    await create_planning_task("In A", _ctx("plan-a"))
    await create_planning_task("In B", _ctx("plan-b"))
    listed_a = await list_planning_tasks(_ctx("plan-a"))
    assert [t["title"] for t in listed_a["tasks"]] == ["In A"]


async def test_get_planning_task_cross_workflow_guard(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine, session_id="plan-a")
    await _seed_planning_session(engine, session_id="plan-b")
    created = await create_planning_task("Owned by A", _ctx("plan-a"))
    template_id = created["id"]

    blocked = await get_planning_task(template_id, _ctx("plan-b"))
    assert "error" in blocked
    allowed = await get_planning_task(template_id, _ctx("plan-a"))
    assert allowed["id"] == template_id


async def test_update_dependencies(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    a = await create_planning_task("A", _ctx())
    b = await create_planning_task("B", _ctx())
    updated = await update_planning_task(b["id"], _ctx(), depends_on_ids=[a["id"]])
    assert updated["depends_on_ids"] == [a["id"]]


async def test_update_dependency_cycle_rejected(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    a = await create_planning_task("A", _ctx())
    b = await create_planning_task("B", _ctx(), depends_on_ids=[a["id"]])
    result = await update_planning_task(a["id"], _ctx(), depends_on_ids=[b["id"]])
    assert "error" in result


async def test_update_preserves_unset_fields(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    created = await create_planning_task("Original", _ctx(), description="desc")
    updated = await update_planning_task(created["id"], _ctx(), position=5)
    assert updated["title"] == "Original"
    assert updated["description"] == "desc"
    assert updated["position"] == 5


async def test_delete_planning_task(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    created = await create_planning_task("Temp", _ctx())
    result = await delete_planning_task(created["id"], _ctx())
    assert result == {"deleted": created["id"]}
    listed = await list_planning_tasks(_ctx())
    assert listed["tasks"] == []


async def test_delete_cross_workflow_guard(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine, session_id="plan-a")
    await _seed_planning_session(engine, session_id="plan-b")
    created = await create_planning_task("A", _ctx("plan-a"))
    result = await delete_planning_task(created["id"], _ctx("plan-b"))
    assert "error" in result


# ---------- session resolution ----------


async def test_resolve_planning_session_tenant(engine: AsyncEngine) -> None:
    workflow_id = await _seed_planning_session(engine, session_id="plan-x")
    async with AsyncSession(engine) as db:
        assert await resolve_planning_session_tenant(db, "plan-x") == (
            workflow_id,
            DEFAULT_TEST_TENANT_ID,
        )
        assert await resolve_planning_session_tenant(db, "absent") is None


# ---------- tool bindings ----------


async def _seed_mcp_server(eng: AsyncEngine, *, name: str = "srv") -> str:
    """Insert an MCPServer owned by the seeded system user and return its id."""
    from models.mcp_server import MCPServer
    from models.user import SYSTEM_USER_ID

    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            url="https://mcp.example.com/mcp",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def test_register_with_tools_binds_them(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    server_id = await _seed_mcp_server(engine)
    result = await register_planning_tasks(
        [
            {
                "key": "t0",
                "title": "Search",
                "tools": [{"server_id": server_id, "tool_name": "search"}],
            }
        ],
        _ctx(),
    )
    assert "error" not in result
    listed = await list_planning_tasks(_ctx())
    assert listed["tasks"][0]["tool_bindings"] == [
        {"server_id": server_id, "tool_name": "search"}
    ]


async def test_register_with_malformed_tools_errors(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
        [{"key": "t0", "title": "Bad", "tools": [{"server_id": "only"}]}], _ctx()
    )
    assert "error" in result
    listed = await list_planning_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_with_unknown_server_errors(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    result = await register_planning_tasks(
        [
            {
                "key": "t0",
                "title": "Bad",
                "tools": [{"server_id": "ghost", "tool_name": "search"}],
            }
        ],
        _ctx(),
    )
    assert "error" in result


async def test_update_replaces_tool_bindings(engine: AsyncEngine) -> None:
    await _seed_planning_session(engine)
    server_id = await _seed_mcp_server(engine)
    created = await create_planning_task(
        "Solo",
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "search"}],
    )
    result = await update_planning_task(
        created["id"],
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "fetch"}],
    )
    assert result["tool_bindings"] == [{"server_id": server_id, "tool_name": "fetch"}]
