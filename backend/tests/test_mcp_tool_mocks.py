"""Integration tests for the MCPToolMock CRUD endpoints."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_tenant, seed_users
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
    await seed_tenant(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def mock_client(mem_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
    from models.mcp_server import (
        MCPServer as _MCPServer,  # noqa: F401 — registers model
    )
    from models.mcp_tool_mock import (
        MCPToolMock as _MCPToolMock,  # noqa: F401 — registers model
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


async def _create_server(client: AsyncClient, name: str = "srv") -> str:
    """Register an MCP server and return its id."""
    body = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": name, "url": "https://mcp.example.com/mcp"},
        ),
        status=201,
    )
    server_id: str = body["id"]
    return server_id


_STRUCTURED = {"kind": "structured", "value": {"ok": True}}


# ---------- create ----------


async def test_create_mock_returns_201(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    body = assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "search returns nothing",
                "mcpServerId": server_id,
                "toolName": "search",
                "responses": [_STRUCTURED],
            },
        ),
        status=201,
    )
    assert body["id"]
    assert body["mcpServerId"] == server_id
    assert body["toolName"] == "search"
    assert body["responses"] == [_STRUCTURED]


async def test_create_mock_accepts_builtin_approval_tool(
    mock_client: AsyncClient,
) -> None:
    body = assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "auto approve",
                "toolName": "request_approval",
                "responses": [{"kind": "structured", "value": {"status": "approved"}}],
            },
        ),
        status=201,
    )
    assert body["mcpServerId"] is None


async def test_create_mock_rejects_unknown_builtin_tool(
    mock_client: AsyncClient,
) -> None:
    """A mock with no server may only name a tool A2Flow knows how to stub."""
    response = await mock_client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": "bogus",
            "toolName": "delete_everything",
            "responses": [_STRUCTURED],
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_mock_rejects_empty_responses(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    response = await mock_client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": "empty",
            "mcpServerId": server_id,
            "toolName": "search",
            "responses": [],
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_mock_rejects_unknown_server(mock_client: AsyncClient) -> None:
    response = await mock_client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": "orphan",
            "mcpServerId": "nope",
            "toolName": "search",
            "responses": [_STRUCTURED],
        },
    )
    err = assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)
    assert err["details"]["entity"] == "MCPServer"


async def test_create_mock_rejects_structured_value_that_is_not_an_object(
    mock_client: AsyncClient,
) -> None:
    server_id = await _create_server(mock_client)
    response = await mock_client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": "scalar",
            "mcpServerId": server_id,
            "toolName": "search",
            "responses": [{"kind": "structured", "value": "plain text"}],
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_mock_rejects_text_value_that_is_not_a_string(
    mock_client: AsyncClient,
) -> None:
    server_id = await _create_server(mock_client)
    response = await mock_client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": "objecty",
            "mcpServerId": server_id,
            "toolName": "search",
            "responses": [{"kind": "text", "value": {"not": "a string"}}],
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_mock_rejects_duplicate_name(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    payload = {
        "name": "same",
        "mcpServerId": server_id,
        "toolName": "search",
        "responses": [_STRUCTURED],
    }
    assert_ok(
        await mock_client.post("/api/v1/mcp-tool-mocks", json=payload), status=201
    )
    response = await mock_client.post("/api/v1/mcp-tool-mocks", json=payload)
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


# ---------- read ----------


async def test_list_mocks_returns_created_records(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    for name in ("a", "b"):
        assert_ok(
            await mock_client.post(
                "/api/v1/mcp-tool-mocks",
                json={
                    "name": name,
                    "mcpServerId": server_id,
                    "toolName": "search",
                    "responses": [_STRUCTURED],
                },
            ),
            status=201,
        )
    body = assert_ok(await mock_client.get("/api/v1/mcp-tool-mocks"))
    assert {item["name"] for item in body} == {"a", "b"}


async def test_list_mocks_filters_by_tool_name(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    for name, tool in (("a", "search"), ("b", "write")):
        assert_ok(
            await mock_client.post(
                "/api/v1/mcp-tool-mocks",
                json={
                    "name": name,
                    "mcpServerId": server_id,
                    "toolName": tool,
                    "responses": [_STRUCTURED],
                },
            ),
            status=201,
        )
    body = assert_ok(
        await mock_client.get("/api/v1/mcp-tool-mocks?q=toolName:eq:write")
    )
    assert [item["name"] for item in body] == ["b"]


async def test_get_unknown_mock_returns_404(mock_client: AsyncClient) -> None:
    assert_err(
        await mock_client.get("/api/v1/mcp-tool-mocks/nope"),
        code="NOT_FOUND",
        status=404,
    )


# ---------- update ----------


async def test_update_mock_replaces_responses(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    created = assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "m",
                "mcpServerId": server_id,
                "toolName": "search",
                "responses": [_STRUCTURED],
            },
        ),
        status=201,
    )
    body = assert_ok(
        await mock_client.patch(
            f"/api/v1/mcp-tool-mocks/{created['id']}",
            json={"responses": [{"kind": "text", "value": "hi"}]},
        )
    )
    assert body["responses"] == [{"kind": "text", "value": "hi"}]


async def test_update_mock_rejects_merged_builtin_target(
    mock_client: AsyncClient,
) -> None:
    """Clearing the server leaves a built-in mock naming an unmockable tool."""
    server_id = await _create_server(mock_client)
    created = assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "m",
                "mcpServerId": server_id,
                "toolName": "search",
                "responses": [_STRUCTURED],
            },
        ),
        status=201,
    )
    response = await mock_client.patch(
        f"/api/v1/mcp-tool-mocks/{created['id']}", json={"mcpServerId": None}
    )
    err = assert_err(response, code="INVALID_MCP_TOOL_MOCK", status=422)
    assert "request_approval" in err["details"]["reason"]


async def test_update_unknown_mock_returns_404(mock_client: AsyncClient) -> None:
    assert_err(
        await mock_client.patch("/api/v1/mcp-tool-mocks/nope", json={"name": "x"}),
        code="NOT_FOUND",
        status=404,
    )


# ---------- delete ----------


async def test_delete_mock_removes_it(mock_client: AsyncClient) -> None:
    server_id = await _create_server(mock_client)
    created = assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "m",
                "mcpServerId": server_id,
                "toolName": "search",
                "responses": [_STRUCTURED],
            },
        ),
        status=201,
    )
    assert_ok(await mock_client.delete(f"/api/v1/mcp-tool-mocks/{created['id']}"))
    assert_err(
        await mock_client.get(f"/api/v1/mcp-tool-mocks/{created['id']}"),
        code="NOT_FOUND",
        status=404,
    )


async def test_delete_unknown_mock_returns_404(mock_client: AsyncClient) -> None:
    assert_err(
        await mock_client.delete("/api/v1/mcp-tool-mocks/nope"),
        code="NOT_FOUND",
        status=404,
    )


async def test_deleting_a_referenced_server_is_still_blocked(
    mock_client: AsyncClient,
) -> None:
    """``ondelete=RESTRICT`` keeps a server that a mock still names."""
    server_id = await _create_server(mock_client)
    assert_ok(
        await mock_client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "m",
                "mcpServerId": server_id,
                "toolName": "search",
                "responses": [_STRUCTURED],
            },
        ),
        status=201,
    )
    assert_err(
        await mock_client.delete(f"/api/v1/mcp-servers/{server_id}"),
        code="CONFLICT_REFERENCED",
        status=409,
    )
