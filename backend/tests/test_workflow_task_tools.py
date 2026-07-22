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
    _resolve_scope,
    create_workflow_task,
    delete_workflow_task,
    get_workflow_task,
    list_workflow_tasks,
    update_workflow_task,
)
from models.notification import Notification, NotificationType
from models.workflow_session import WorkflowSession
from repositories import SqlNotificationRepository, SqlWorkflowSessionRepository
from repositories.tenant_bootstrap import NoTenantSessionError
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


async def _seed_session(
    eng: AsyncEngine,
    *,
    session_id: str = "sess-abc",
    user_id: str = "owner",
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a WorkflowSession with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        ws = WorkflowSession(
            session_id=session_id,
            workflow_name="wf",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            user_id=user_id,
            tenant_id=tenant_id,
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


async def test_resolve_scope(engine: AsyncEngine) -> None:
    ws_id = await _seed_session(engine, session_id="sess-x")
    async with AsyncSession(engine) as db:
        assert await _resolve_scope(_ctx("sess-x"), db) == (
            ws_id,
            DEFAULT_TEST_TENANT_ID,
        )
        with pytest.raises(NoTenantSessionError):
            await _resolve_scope(_ctx("absent"), db)


async def test_get_by_session_id(engine: AsyncEngine) -> None:
    ws_id = await _seed_session(engine, session_id="sess-find")
    async with AsyncSession(engine) as db:
        repo = SqlWorkflowSessionRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        found = await repo.get_by_session_id("sess-find")
        assert found is not None
        assert found.id == ws_id
        assert await repo.get_by_session_id("absent") is None


async def _notifications_for(eng: AsyncEngine, user_id: str) -> list[Notification]:
    """Return all notifications addressed to ``user_id`` via the repository."""
    async with AsyncSession(eng) as db:
        repo = SqlNotificationRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        return await repo.list(user_id=user_id, limit=100, offset=0)


async def test_session_completed_notification_emitted_once(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine, user_id="owner")
    a = await create_workflow_task("A", _ctx())
    b = await create_workflow_task("B", _ctx())

    # Not every task is terminal yet: no completion notification.
    await update_workflow_task(a["id"], _ctx(), status="completed")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.session_completed
    ]
    assert completed == []

    # Final task reaches a terminal state: exactly one completion notification.
    await update_workflow_task(b["id"], _ctx(), status="failed")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.session_completed
    ]
    assert len(completed) == 1

    # A further terminal-state update must not create a duplicate.
    await update_workflow_task(a["id"], _ctx(), status="skipped")
    completed = [
        n
        for n in await _notifications_for(engine, "owner")
        if n.type is NotificationType.session_completed
    ]
    assert len(completed) == 1


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


async def test_create_workflow_task_with_tool_bindings(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    result = await create_workflow_task(
        "Solo",
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "search"}],
    )
    assert result["tool_bindings"] == [{"server_id": server_id, "tool_name": "search"}]


async def test_create_workflow_task_with_malformed_bindings_errors(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    result = await create_workflow_task(
        "Solo", _ctx(), tool_bindings=[{"tool_name": "search"}]
    )
    assert "error" in result


async def test_update_workflow_task_replaces_tool_bindings(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    created = await create_workflow_task(
        "Solo",
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "search"}],
    )
    result = await update_workflow_task(
        created["id"],
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "fetch"}],
    )
    assert result["tool_bindings"] == [{"server_id": server_id, "tool_name": "fetch"}]


async def test_update_workflow_task_keeps_bindings_when_omitted(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    created = await create_workflow_task(
        "Solo",
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "search"}],
    )
    result = await update_workflow_task(created["id"], _ctx(), title="Renamed")
    assert result["tool_bindings"] == [{"server_id": server_id, "tool_name": "search"}]


# ---------- tenant isolation ----------


async def test_get_workflow_task_cross_tenant_guard(engine: AsyncEngine) -> None:
    """A task created under one tenant's session is invisible from another's.

    Both sessions use distinct ADK session ids (the normal case): the tenant
    boundary is enforced by the resolved tenant id, not by session-id
    collision, so this confirms the bootstrap-resolution path picks the
    correct tenant for each call and that the underlying repositories filter
    on it.
    """
    await seed_tenant(engine, "tenant-other")
    await _seed_session(
        engine, session_id="sess-tenant-a", tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _seed_session(engine, session_id="sess-tenant-b", tenant_id="tenant-other")
    created = await create_workflow_task("Tenant A's task", _ctx("sess-tenant-a"))

    blocked = await get_workflow_task(created["id"], _ctx("sess-tenant-b"))
    assert "error" in blocked
    allowed = await get_workflow_task(created["id"], _ctx("sess-tenant-a"))
    assert allowed["id"] == created["id"]
