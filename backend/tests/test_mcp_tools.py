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

from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from infrastructure.mcp_tools import call_mcp_tool, list_mcp_tools
from infrastructure.secret_cipher import get_secret_cipher
from models.agent_skill import AgentSkill
from models.mcp_server import MCPServer, McpTransport
from models.secret import Secret, SecretType
from models.user import SYSTEM_USER_ID
from models.workflow import Workflow
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.exceptions import McpConnectionError
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


async def _seed_design_session(
    eng: AsyncEngine,
    *,
    session_id: str = "design-abc",
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a skill + workflow whose design session is ``session_id``.

    Workflow generation and the design chat run against a Workflow's design
    session rather than a WorkflowExecution, so this is what the tools see
    during the whole design phase.

    Returns:
        The workflow's primary key.
    """
    async with AsyncSession(eng) as db:
        skill = AgentSkill(
            name=f"skill-{session_id}",
            repo_url="https://example.com/repo",
            repo_path="",
            tenant_id=tenant_id,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)
        skill_id = skill.id

        workflow = Workflow(
            name=f"wf-{session_id}",
            agent_skill_id=skill_id,
            session_id=session_id,
            agent_skill_commit_sha="a" * 40,
            tenant_id=tenant_id,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow.id


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


def _ctx(session_id: str = "sess-abc", user_id: str = "tester") -> Any:
    """Build a fake ToolContext exposing ``session.id`` and ``user_id``."""
    return SimpleNamespace(session=SimpleNamespace(id=session_id), user_id=user_id)


async def _seed_server(
    eng: AsyncEngine,
    *,
    name: str = "srv",
    url: str = "https://mcp.example.com/mcp",
    headers: dict[str, str] | None = None,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a streamable-HTTP MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.streamable_http,
            url=url,
            headers=headers or {},
            tenant_id=tenant_id,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_stdio_server(
    eng: AsyncEngine,
    *,
    name: str = "stdio-srv",
    command: str = "npx",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Insert a stdio MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.stdio,
            command=command,
            args=args if args is not None else ["-y", "pkg"],
            env=env or {},
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_session(eng: AsyncEngine, *, session_id: str = "sess-abc") -> str:
    """Insert a WorkflowExecution with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=session_id,
            workflow_name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            initiator_id=SYSTEM_USER_ID,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_task(
    eng: AsyncEngine,
    execution_id: str,
    *,
    status: WorkflowTaskStatus = WorkflowTaskStatus.in_progress,
    bindings: list[tuple[str, str]] = (),  # type: ignore[assignment]
) -> str:
    """Insert a WorkflowTask with optional (server_id, tool_name) bindings."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Step",
            status=status,
            tenant_id=DEFAULT_TEST_TENANT_ID,
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
    execution_id = await _seed_session(engine)
    await _seed_task(
        engine,
        execution_id,
        status=WorkflowTaskStatus.pending,
        bindings=[(server_id, "search")],
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "in_progress" in result["error"]


async def test_call_unbound_tool_rejected_with_bound_list(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    result = await call_mcp_tool(server_id, "delete_everything", {}, _ctx())
    assert "not bound" in result["error"]
    assert "search" in result["error"]


async def test_call_bound_tool_forwards_to_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine, headers={"Authorization": "Bearer t"})
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen.update(connection=connection, tool_name=tool_name, arguments=arguments)
        return _tool_result("found it", structured={"hits": 1})

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {"q": "a2flow"}, _ctx())
    assert result == {"result": {"content": ["found it"], "structured": {"hits": 1}}}
    assert seen["connection"] == HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "Bearer t"}
    )
    assert seen["tool_name"] == "search"
    assert seen["arguments"] == {"q": "a2flow"}


async def test_call_accepts_json_string_arguments(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        connection: McpConnection,
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
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    result = await call_mcp_tool(server_id, "search", "not json", _ctx())  # type: ignore[arg-type]
    assert "error" in result


async def test_call_unreachable_server_errors(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])

    async def fake_call_server_tool(
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        raise McpConnectionError(connection.label, "connection refused")

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "unreachable" in result["error"]


async def test_call_tool_error_result_becomes_error_dict(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])

    async def fake_call_server_tool(
        connection: McpConnection,
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
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "alpha")])
    await _seed_task(engine, execution_id, bindings=[(server_id, "beta")])

    async def fake_call_server_tool(
        connection: McpConnection,
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


async def test_call_forwards_a_stdio_server_as_a_stdio_connection(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_local_secret(engine, "files-key", "tok-stdio")
    server_id = await _seed_stdio_server(
        engine,
        command="npx",
        args=["-y", "files-mcp@0.3.0"],
        env={"API_KEY": "${secret:files-key/k}"},
    )
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "read_file")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen["connection"] = connection
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "read_file", {}, _ctx())
    assert "error" not in result
    assert seen["connection"] == StdioConnection(
        command="npx",
        args=["-y", "files-mcp@0.3.0"],
        env={"API_KEY": "tok-stdio"},
    )


# ---------- list_mcp_tools ----------


async def test_list_mcp_tools_without_session_errors(engine: AsyncEngine) -> None:
    result = await list_mcp_tools(_ctx("unknown-session"))
    assert "error" in result


async def test_list_mcp_tools_empty_registry(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await list_mcp_tools(_ctx())
    assert result == {"servers": []}


async def test_list_mcp_tools_works_in_a_design_session(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The design agents must see the registry: that is where tools get bound.

    Their ADK session is keyed on a Workflow, not a WorkflowExecution, so
    resolving the run through WorkflowExecution alone silently left every
    generated task templates without tool bindings.
    """
    await _seed_design_session(engine)
    server_id = await _seed_server(engine, name="design-visible")

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
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
    result = await list_mcp_tools(_ctx("design-abc"))
    assert "error" not in result
    assert [entry["server_id"] for entry in result["servers"]] == [server_id]
    assert result["servers"][0]["tools"][0]["name"] == "search"


async def test_list_mcp_tools_from_design_session_stays_tenant_scoped(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Widening the resolver must not widen which tenant's servers are visible."""
    await seed_tenant(engine, "tenant-other")
    await _seed_design_session(engine, session_id="design-mine")
    mine = await _seed_server(engine, name="mine")
    await _seed_server(engine, name="theirs", tenant_id="tenant-other")

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    result = await list_mcp_tools(_ctx("design-mine"))
    assert [entry["server_id"] for entry in result["servers"]] == [mine]


async def test_call_mcp_tool_still_rejects_a_design_session(
    engine: AsyncEngine,
) -> None:
    """Design may bind tools, but only an execution run may invoke them."""
    await _seed_design_session(engine, session_id="design-only")
    server_id = await _seed_server(engine)
    result = await call_mcp_tool(server_id, "search", {}, _ctx("design-only"))
    assert "error" in result


async def test_list_mcp_tools_aggregates_and_isolates_failures(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_session(engine)
    good_id = await _seed_server(engine, name="good", url="https://good/mcp")
    bad_id = await _seed_server(engine, name="bad", url="https://bad/mcp")

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        if "bad" in connection.label:
            raise McpConnectionError(connection.label, "connection refused")
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
    """Insert a local Secret holding one ``k`` entry encrypted with the process cipher."""
    async with AsyncSession(eng) as db:
        db.add(
            Secret(
                name=name,
                type=SecretType.local,
                entries={"k": get_secret_cipher().encrypt(value)},
                tenant_id=DEFAULT_TEST_TENANT_ID,
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
        engine, headers={"Authorization": "Bearer ${secret:api-token/k}"}
    )
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        seen["connection"] = connection
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "error" not in result
    assert seen["connection"] == HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "Bearer tok-xyz"}
    )


async def test_call_with_missing_secret_returns_error(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(
        engine, headers={"Authorization": "Bearer ${secret:nope/k}"}
    )
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    called: list[str] = []

    async def fake_call_server_tool(
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> types.CallToolResult:
        called.append(connection.label)
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
    await _seed_session(engine)
    await _seed_local_secret(engine, "good-token", "tok-1")
    good_id = await _seed_server(
        engine,
        name="good",
        url="https://good/mcp",
        headers={"Authorization": "Bearer ${secret:good-token/k}"},
    )
    bad_id = await _seed_server(
        engine,
        name="bad",
        url="https://bad/mcp",
        headers={"Authorization": "Bearer ${secret:missing/k}"},
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        seen[connection.label] = connection
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    result = await list_mcp_tools(_ctx())
    by_id = {entry["server_id"]: entry for entry in result["servers"]}
    assert by_id[good_id]["tools"] == []
    assert "cannot resolve secret 'missing'" in by_id[bad_id]["error"]
    assert seen == {
        "https://good/mcp": HttpConnection(
            url="https://good/mcp", headers={"Authorization": "Bearer tok-1"}
        )
    }
