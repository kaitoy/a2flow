"""Tests for the MCP proxy agent tools in ``infrastructure.mcp_tools``.

Like the WorkflowTask tool tests, each test monkeypatches the module-level
database engine to an isolated in-memory SQLite database and drives the tools
with a lightweight fake ToolContext. Remote MCP traffic is faked by
monkeypatching ``infrastructure.mcp_client``.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from mcp import types
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_tools import call_mcp_tool, list_mcp_tools
from infrastructure.secret_cipher import get_secret_cipher
from models.mcp_server import MCPServer
from models.secret import Secret, SecretType
from models.user import SYSTEM_USER_ID
from models.workflow_session import WorkflowSession
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.exceptions import McpConnectionError
from tests._seed import seed_users


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

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


def _ctx(session_id: str = "sess-abc", user_id: str = "tester") -> Any:
    """Build a fake ToolContext exposing ``session.id`` and ``user_id``."""
    return SimpleNamespace(session=SimpleNamespace(id=session_id), user_id=user_id)


async def _seed_server(
    eng: AsyncEngine,
    *,
    name: str = "srv",
    url: str = "https://mcp.example.com/mcp",
    headers: dict[str, str] | None = None,
) -> str:
    """Insert an MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            url=url,
            headers=headers or {},
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_session(eng: AsyncEngine, *, session_id: str = "sess-abc") -> str:
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
            user_id=SYSTEM_USER_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.id


async def _seed_task(
    eng: AsyncEngine,
    ws_id: str,
    *,
    status: WorkflowTaskStatus = WorkflowTaskStatus.in_progress,
    bindings: list[tuple[str, str]] = (),  # type: ignore[assignment]
) -> str:
    """Insert a WorkflowTask with optional (server_id, tool_name) bindings."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_session_id=ws_id,
            title="Step",
            status=status,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        for server_id, tool_name in bindings:
            db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id, mcp_server_id=server_id, tool_name=tool_name
                )
            )
        await db.commit()
        return task_id


def _tool_result(
    text: str = "ok",
    *,
    is_error: bool = False,
    structured: dict[str, Any] | None = None,
) -> types.CallToolResult:
    """Build a CallToolResult with a single text block."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=is_error,
        structuredContent=structured,
    )


# ---------- call_mcp_tool ----------


async def test_call_without_session_errors(engine: AsyncEngine) -> None:
    result = await call_mcp_tool("srv-1", "search", {}, _ctx("unknown-session"))
    assert "error" in result


async def test_call_without_in_progress_task_errors(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(
        engine,
        ws_id,
        status=WorkflowTaskStatus.pending,
        bindings=[(server_id, "search")],
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "in_progress" in result["error"]


async def test_call_unbound_tool_rejected_with_bound_list(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    result = await call_mcp_tool(server_id, "delete_everything", {}, _ctx())
    assert "not bound" in result["error"]
    assert "search" in result["error"]


async def test_call_bound_tool_forwards_to_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine, headers={"Authorization": "Bearer t"})
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen.update(url=url, headers=headers, tool_name=tool_name, arguments=arguments)
        return _tool_result("found it", structured={"hits": 1})

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {"q": "a2flow"}, _ctx())
    assert result == {"result": {"content": ["found it"], "structured": {"hits": 1}}}
    assert seen["url"] == "https://mcp.example.com/mcp"
    assert seen["headers"] == {"Authorization": "Bearer t"}
    assert seen["tool_name"] == "search"
    assert seen["arguments"] == {"q": "a2flow"}


async def test_call_accepts_json_string_arguments(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen["arguments"] = arguments
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", '{"q": "x"}', _ctx())  # type: ignore[arg-type]
    assert "error" not in result
    assert seen["arguments"] == {"q": "x"}


async def test_call_invalid_arguments_rejected(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    result = await call_mcp_tool(server_id, "search", "not json", _ctx())  # type: ignore[arg-type]
    assert "error" in result


async def test_call_unreachable_server_errors(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        raise McpConnectionError(url, "connection refused")

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "unreachable" in result["error"]


async def test_call_tool_error_result_becomes_error_dict(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        return _tool_result("boom", is_error=True)

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert result == {"error": "boom"}


async def test_call_validates_against_union_of_in_progress_tasks(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "alpha")])
    await _seed_task(engine, ws_id, bindings=[(server_id, "beta")])

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    for tool_name in ("alpha", "beta"):
        result = await call_mcp_tool(server_id, tool_name, {}, _ctx())
        assert "error" not in result


# ---------- list_mcp_tools ----------


async def test_list_mcp_tools_empty_registry(engine: AsyncEngine) -> None:
    result = await list_mcp_tools(_ctx())
    assert result == {"servers": []}


async def test_list_mcp_tools_aggregates_and_isolates_failures(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    good_id = await _seed_server(engine, name="good", url="https://good/mcp")
    bad_id = await _seed_server(engine, name="bad", url="https://bad/mcp")

    async def fake_list_server_tools(
        url: str, headers: dict[str, str] | None = None
    ) -> list[Any]:
        if "bad" in url:
            raise McpConnectionError(url, "connection refused")
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
    result = await list_mcp_tools(_ctx())
    by_id = {entry["server_id"]: entry for entry in result["servers"]}
    assert by_id[good_id]["tools"] == [
        {
            "name": "search",
            "description": "Search the web",
            "input_schema": {"type": "object"},
        }
    ]
    assert "unreachable" in by_id[bad_id]["error"]


# ---------- secret placeholder resolution ----------


async def _seed_local_secret(eng: AsyncEngine, name: str, value: str) -> None:
    """Insert a local Secret whose value is encrypted with the process cipher."""
    async with AsyncSession(eng) as db:
        db.add(
            Secret(
                name=name,
                type=SecretType.local,
                value=get_secret_cipher().encrypt(value),
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()


async def test_call_resolves_secret_placeholder_in_headers(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_local_secret(engine, "api-token", "tok-xyz")
    server_id = await _seed_server(
        engine, headers={"Authorization": "Bearer ${secret:api-token}"}
    )
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen["headers"] = headers
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "error" not in result
    assert seen["headers"] == {"Authorization": "Bearer tok-xyz"}


async def test_call_with_missing_secret_returns_error(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(
        engine, headers={"Authorization": "Bearer ${secret:nope}"}
    )
    ws_id = await _seed_session(engine)
    await _seed_task(engine, ws_id, bindings=[(server_id, "search")])
    called: list[str] = []

    async def fake_call_server_tool(
        url: str,
        headers: dict[str, str] | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        called.append(url)
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "cannot resolve secret 'nope'" in result["error"]
    assert called == []


async def test_list_mcp_tools_isolates_secret_resolution_failure(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_local_secret(engine, "good-token", "tok-1")
    good_id = await _seed_server(
        engine,
        name="good",
        url="https://good/mcp",
        headers={"Authorization": "Bearer ${secret:good-token}"},
    )
    bad_id = await _seed_server(
        engine,
        name="bad",
        url="https://bad/mcp",
        headers={"Authorization": "Bearer ${secret:missing}"},
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(
        url: str, headers: dict[str, str] | None = None
    ) -> list[Any]:
        seen[url] = headers
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    result = await list_mcp_tools(_ctx())
    by_id = {entry["server_id"]: entry for entry in result["servers"]}
    assert by_id[good_id]["tools"] == []
    assert "cannot resolve secret 'missing'" in by_id[bad_id]["error"]
    assert seen == {"https://good/mcp": {"Authorization": "Bearer tok-1"}}
