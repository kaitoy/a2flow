"""Integration tests for the MCPServer CRUD endpoints and tool discovery."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from repositories.exceptions import McpConnectionError
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def mem_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield an isolated in-memory engine with the schema created and users seeded."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def mcp_client(mem_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
    from models.mcp_server import (
        MCPServer as _MCPServer,  # noqa: F401 — registers model
    )

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


_CREATE_BODY = {
    "name": "My MCP Server",
    "url": "https://mcp.example.com/mcp",
    "headers": {"Authorization": "Bearer secret"},
}


# ---------- create ----------


async def test_create_server_returns_201(mcp_client: AsyncClient) -> None:
    response = await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_server_response_has_fields(mcp_client: AsyncClient) -> None:
    body = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    assert body["id"]
    assert body["name"] == "My MCP Server"
    assert body["url"] == "https://mcp.example.com/mcp"
    assert body["headers"] == {"Authorization": "Bearer secret"}


async def test_create_server_headers_default_to_empty(mcp_client: AsyncClient) -> None:
    body = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers", json={"name": "Bare", "url": "https://x/mcp"}
        ),
        status=201,
    )
    assert body["headers"] == {}


async def test_create_server_missing_url_returns_422(mcp_client: AsyncClient) -> None:
    response = await mcp_client.post("/api/v1/mcp-servers", json={"name": "X"})
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_server_duplicate_name_returns_409(
    mcp_client: AsyncClient,
) -> None:
    await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY)
    response = await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY)
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


# ---------- list ----------


async def test_list_servers_empty_initially(mcp_client: AsyncClient) -> None:
    response = await mcp_client.get("/api/v1/mcp-servers")
    assert assert_ok(response) == []


async def test_list_servers_returns_created(mcp_client: AsyncClient) -> None:
    await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY)
    response = await mcp_client.get("/api/v1/mcp-servers")
    assert len(assert_ok(response)) == 1


# ---------- get ----------


async def test_get_server_returns_correct_data(mcp_client: AsyncClient) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}")
    assert assert_ok(response)["name"] == "My MCP Server"


async def test_get_server_unknown_id_returns_404(mcp_client: AsyncClient) -> None:
    response = await mcp_client.get("/api/v1/mcp-servers/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_server_replaces_headers(mcp_client: AsyncClient) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"headers": {"X-Api-Key": "k"}}
    )
    body = assert_ok(response)
    assert body["headers"] == {"X-Api-Key": "k"}
    assert body["name"] == "My MCP Server"


async def test_update_server_duplicate_name_returns_409(
    mcp_client: AsyncClient,
) -> None:
    await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY)
    other = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers", json={"name": "Other", "url": "https://y/mcp"}
        ),
        status=201,
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{other['id']}", json={"name": "My MCP Server"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_update_server_unknown_id_returns_404(mcp_client: AsyncClient) -> None:
    response = await mcp_client.patch(
        "/api/v1/mcp-servers/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_server_returns_200(mcp_client: AsyncClient) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.delete(f"/api/v1/mcp-servers/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_server_unknown_id_returns_404(mcp_client: AsyncClient) -> None:
    response = await mcp_client.delete("/api/v1/mcp-servers/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_server_referenced_by_binding_returns_409(
    mcp_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    from models.workflow_session import WorkflowSession
    from models.workflow_task import WorkflowTask, WorkflowTaskToolBinding

    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    async with AsyncSession(mem_engine) as db:
        ws = WorkflowSession(
            session_id="sess-1",
            workflow_name="wf",
            workflow_prompt="p",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            user_id=SYSTEM_USER_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        task = WorkflowTask(
            workflow_session_id=ws.id,
            title="Step",
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        db.add(
            WorkflowTaskToolBinding(
                task_id=task.id, mcp_server_id=created["id"], tool_name="search"
            )
        )
        await db.commit()

    response = await mcp_client.delete(f"/api/v1/mcp-servers/{created['id']}")
    assert_err(response, code="CONFLICT_REFERENCED", status=409)


# ---------- tool discovery ----------


async def test_list_server_tools_returns_tools(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(
        url: str, headers: dict[str, str] | None = None
    ) -> list[Any]:
        seen["url"] = url
        seen["headers"] = headers
        return [
            SimpleNamespace(
                name="search",
                description="Search the web",
                inputSchema={"type": "object"},
            )
        ]

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools")
    tools = assert_ok(response)
    assert tools == [
        {
            "name": "search",
            "description": "Search the web",
            "inputSchema": {"type": "object"},
        }
    ]
    assert seen["url"] == _CREATE_BODY["url"]
    assert seen["headers"] == _CREATE_BODY["headers"]


async def test_list_server_tools_unreachable_returns_502(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )

    async def fake_list_server_tools(
        url: str, headers: dict[str, str] | None = None
    ) -> list[Any]:
        raise McpConnectionError(url, "connection refused")

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools")
    assert_err(response, code="MCP_UNREACHABLE", status=502)


async def test_list_server_tools_unknown_id_returns_404(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.get("/api/v1/mcp-servers/nonexistent/tools")
    assert_err(response, code="NOT_FOUND", status=404)
