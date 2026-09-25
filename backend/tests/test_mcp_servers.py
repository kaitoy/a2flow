"""Integration tests for the MCPServer CRUD endpoints and tool discovery."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from models.secret import Secret as _Secret  # noqa: F401 — registers model
from models.user import SYSTEM_USER_ID
from repositories.exceptions import McpConnectionError
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def mem_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine with the schema created and users seeded."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)
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
    "name": "my-mcp-server",
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
    assert body["name"] == "my-mcp-server"
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


async def test_create_server_rejects_loopback_url(mcp_client: AsyncClient) -> None:
    """A url whose host is the loopback address returns 422 (SSRF guard)."""
    response = await mcp_client.post(
        "/api/v1/mcp-servers",
        json={"name": "Bad", "url": "http://127.0.0.1/mcp"},
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_server_rejects_url_resolving_to_private_ip(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A url whose host resolves to a private IP returns 422 (SSRF guard)."""
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )
    response = await mcp_client.post(
        "/api/v1/mcp-servers",
        json={"name": "Bad", "url": "http://internal.example.com/mcp"},
    )
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
    assert assert_ok(response)["name"] == "my-mcp-server"


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
    assert body["name"] == "my-mcp-server"


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
        f"/api/v1/mcp-servers/{other['id']}", json={"name": "my-mcp-server"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_update_server_unknown_id_returns_404(mcp_client: AsyncClient) -> None:
    response = await mcp_client.patch(
        "/api/v1/mcp-servers/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_update_server_rejects_url_resolving_to_private_ip(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patching url to a host resolving to a private IP returns 422 (SSRF guard)."""
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.1.2.3"]
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"url": "http://internal.example.com/mcp"},
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- stdio transport ----------


_STDIO_BODY = {
    "name": "local-files",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "files-mcp@0.3.0"],
    "env": {"API_KEY": "tok"},
}


async def test_create_stdio_server_returns_201_with_its_fields(
    mcp_client: AsyncClient,
) -> None:
    body = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    assert body["transport"] == "stdio"
    assert body["command"] == "npx"
    assert body["args"] == ["-y", "files-mcp@0.3.0"]
    assert body["env"] == {"API_KEY": "tok"}
    assert body["url"] is None


async def test_create_stdio_server_without_command_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers", json={"name": "X", "transport": "stdio"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_stdio_server_with_url_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers",
        json={**_STDIO_BODY, "url": "https://mcp.example.com/mcp"},
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_http_server_with_command_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers", json={**_CREATE_BODY, "command": "npx"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_stdio_server_with_unsupported_command_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers", json={**_STDIO_BODY, "command": "python3"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_patch_stdio_server_with_unsupported_command_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"command": "/usr/bin/python3"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_stdio_server_skips_the_url_safety_check(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stdio server opens no socket, so DNS resolution must not gate it."""

    def _fail(host: str) -> list[str]:
        raise AssertionError("url safety must not be checked for a stdio server")

    monkeypatch.setattr("infrastructure.url_safety.resolve_host", _fail)
    assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )


async def test_patch_stdio_field_on_http_server_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"command": "npx"}
    )
    err = assert_err(response, code="INVALID_MCP_SERVER", status=422)
    assert "command" in err["details"]["reason"]


async def test_patch_url_on_stdio_server_returns_422(mcp_client: AsyncClient) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"url": "https://mcp.example.com/mcp"},
    )
    assert_err(response, code="INVALID_MCP_SERVER", status=422)


async def test_patch_switching_to_stdio_clears_url_and_headers(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    body = assert_ok(
        await mcp_client.patch(
            f"/api/v1/mcp-servers/{created['id']}",
            json={"transport": "stdio", "command": "uvx", "args": ["pkg"]},
        )
    )
    assert body["transport"] == "stdio"
    assert body["command"] == "uvx"
    assert body["url"] is None
    assert body["headers"] == {}


async def test_patch_switching_to_stdio_without_command_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"transport": "stdio"}
    )
    assert_err(response, code="INVALID_MCP_SERVER", status=422)


async def test_patch_switching_to_http_clears_command_args_and_env(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    body = assert_ok(
        await mcp_client.patch(
            f"/api/v1/mcp-servers/{created['id']}",
            json={"transport": "streamable_http", "url": "https://mcp.example.com/mcp"},
        )
    )
    assert body["transport"] == "streamable_http"
    assert body["url"] == "https://mcp.example.com/mcp"
    assert body["command"] is None
    assert body["args"] == []
    assert body["env"] == {}


# ---------- script transport ----------


_SCRIPT_BODY = {
    "name": "calc",
    "transport": "script",
    "language": "python",
    "source": "def add(a: int, b: int) -> int:\n    return a + b\n",
    "env": {"API_KEY": "tok"},
}


async def test_create_script_server_returns_201_with_its_fields(
    mcp_client: AsyncClient,
) -> None:
    body = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_SCRIPT_BODY), status=201
    )
    assert body["transport"] == "script"
    assert body["language"] == "python"
    assert body["source"] == _SCRIPT_BODY["source"]
    assert body["env"] == {"API_KEY": "tok"}
    assert body["command"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": None},
        {"language": None},
        {"command": "npx"},
        {"url": "https://mcp.example.com/mcp"},
        {"source": "def broken(:\n"},
    ],
    ids=["no-source", "no-language", "command", "url", "syntax-error"],
)
async def test_create_invalid_script_server_returns_422(
    mcp_client: AsyncClient, overrides: dict[str, Any]
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers", json={**_SCRIPT_BODY, **overrides}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_javascript_script_server_skips_the_syntax_check(
    mcp_client: AsyncClient,
) -> None:
    """The backend has no Node.js, so a JavaScript source is stored as is."""
    body = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={**_SCRIPT_BODY, "language": "javascript", "source": "export {"},
        ),
        status=201,
    )
    assert body["language"] == "javascript"


async def test_create_stdio_server_with_source_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers", json={**_STDIO_BODY, "source": "x = 1"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_patch_script_source_with_syntax_error_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_SCRIPT_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"source": "def broken(:\n"}
    )
    err = assert_err(response, code="INVALID_MCP_SERVER", status=422)
    assert "line 1" in err["details"]["reason"]


async def test_patch_switching_script_to_python_checks_the_stored_source(
    mcp_client: AsyncClient,
) -> None:
    """Changing only the language re-checks the source already stored."""
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={**_SCRIPT_BODY, "language": "javascript", "source": "export {"},
        ),
        status=201,
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"language": "python"}
    )
    assert_err(response, code="INVALID_MCP_SERVER", status=422)


async def test_patch_command_on_script_server_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_SCRIPT_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"command": "npx"}
    )
    err = assert_err(response, code="INVALID_MCP_SERVER", status=422)
    assert "command" in err["details"]["reason"]


async def test_patch_switching_stdio_to_script_clears_command_and_keeps_env(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    body = assert_ok(
        await mcp_client.patch(
            f"/api/v1/mcp-servers/{created['id']}",
            json={
                "transport": "script",
                "language": "python",
                "source": _SCRIPT_BODY["source"],
            },
        )
    )
    assert body["transport"] == "script"
    assert body["command"] is None
    assert body["args"] == []
    assert body["env"] == {"API_KEY": "tok"}


async def test_patch_switching_to_script_without_source_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"transport": "script", "language": "python"},
    )
    err = assert_err(response, code="INVALID_MCP_SERVER", status=422)
    assert "source" in err["details"]["reason"]


async def test_patch_switching_script_to_http_clears_language_source_and_env(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_SCRIPT_BODY), status=201
    )
    body = assert_ok(
        await mcp_client.patch(
            f"/api/v1/mcp-servers/{created['id']}",
            json={"transport": "streamable_http", "url": "https://mcp.example.com/mcp"},
        )
    )
    assert body["transport"] == "streamable_http"
    assert body["language"] is None
    assert body["source"] is None
    assert body["env"] == {}


async def test_list_stdio_server_tools_uses_a_stdio_connection(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert_ok(
        await mcp_client.post(
            "/api/v1/secrets",
            json={"name": "files-key", "type": "local", "entries": {"k": "tok-xyz"}},
        ),
        status=201,
    )
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={**_STDIO_BODY, "env": {"API_KEY": "${secret:files-key/k}"}},
        ),
        status=201,
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        seen["connection"] = connection
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    assert_ok(await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools"))
    assert seen["connection"] == StdioConnection(
        command="npx", args=["-y", "files-mcp@0.3.0"], env={"API_KEY": "tok-xyz"}
    )


async def test_stdio_server_unreachable_error_omits_env(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        raise McpConnectionError(connection.label, "no such file or directory")

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools")
    err = assert_err(response, code="MCP_UNREACHABLE", status=502)
    assert err["details"] == {"server": "npx -y files-mcp@0.3.0"}
    assert "tok" not in response.text


# ---------- ${env:NAME} in args ----------


async def test_create_stdio_server_with_env_arg_reference_returns_201(
    mcp_client: AsyncClient,
) -> None:
    body = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={**_STDIO_BODY, "args": ["--token", "${env:API_KEY}"]},
        ),
        status=201,
    )
    assert body["args"] == ["--token", "${env:API_KEY}"]


async def test_create_stdio_server_with_undefined_env_arg_reference_returns_422(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers",
        json={**_STDIO_BODY, "args": ["${env:MISSING}"]},
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_patch_stdio_server_args_referencing_undefined_env_var_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_STDIO_BODY), status=201
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}",
        json={"args": ["${env:MISSING}"]},
    )
    err = assert_err(response, code="INVALID_MCP_SERVER", status=422)
    assert "MISSING" in err["details"]["reason"]


async def test_patch_stdio_server_removing_referenced_env_var_returns_422(
    mcp_client: AsyncClient,
) -> None:
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={**_STDIO_BODY, "args": ["${env:API_KEY}"]},
        ),
        status=201,
    )
    response = await mcp_client.patch(
        f"/api/v1/mcp-servers/{created['id']}", json={"env": {}}
    )
    assert_err(response, code="INVALID_MCP_SERVER", status=422)


async def test_list_stdio_server_tools_expands_env_placeholder_in_args(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``${env:NAME}`` in ``args`` picks up the secret-resolved ``env`` value,
    and the resulting connection's label never echoes it back."""
    assert_ok(
        await mcp_client.post(
            "/api/v1/secrets",
            json={"name": "files-key", "type": "local", "entries": {"k": "tok-xyz"}},
        ),
        status=201,
    )
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={
                **_STDIO_BODY,
                "args": ["-y", "files-mcp@0.3.0", "--token", "${env:API_KEY}"],
                "env": {"API_KEY": "${secret:files-key/k}"},
            },
        ),
        status=201,
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        seen["connection"] = connection
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    assert_ok(await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools"))
    connection = seen["connection"]
    assert isinstance(connection, StdioConnection)
    assert connection.args == ["-y", "files-mcp@0.3.0", "--token", "tok-xyz"]
    assert "tok-xyz" not in connection.label


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
    from models.workflow_execution import WorkflowExecution
    from models.workflow_task import WorkflowTask, WorkflowTaskToolBinding

    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )
    async with AsyncSession(mem_engine) as db:
        execution = WorkflowExecution(
            session_id="sess-1",
            name="wf",
            workflow_prompt="p",
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
        task = WorkflowTask(
            workflow_execution_id=execution.id,
            title="Step",
            tenant_id=DEFAULT_TEST_TENANT_ID,
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

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        seen["connection"] = connection
        return [
            SimpleNamespace(
                name="search",
                description="Search the web",
                inputSchema={"type": "object"},
                outputSchema={
                    "type": "object",
                    "properties": {"hits": {"type": "array"}},
                },
            ),
            # A server on an older spec revision advertises no output schema.
            SimpleNamespace(
                name="ping",
                description=None,
                inputSchema={"type": "object"},
                outputSchema=None,
            ),
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
            "outputSchema": {
                "type": "object",
                "properties": {"hits": {"type": "array"}},
            },
        },
        {
            "name": "ping",
            "description": None,
            "inputSchema": {"type": "object"},
            "outputSchema": None,
        },
    ]
    assert seen["connection"] == HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "Bearer secret"}
    )


async def test_list_server_tools_unreachable_returns_502(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = assert_ok(
        await mcp_client.post("/api/v1/mcp-servers", json=_CREATE_BODY), status=201
    )

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        raise McpConnectionError(connection.label, "connection refused")

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools")
    err = assert_err(response, code="MCP_UNREACHABLE", status=502)
    assert err["details"] == {"server": _CREATE_BODY["url"]}
    assert "connection refused" not in response.text


async def test_list_server_tools_unknown_id_returns_404(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.get("/api/v1/mcp-servers/nonexistent/tools")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_list_server_tools_resolves_secret_placeholders(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """${secret:NAME/KEY} placeholders in headers are expanded before connecting."""
    assert_ok(
        await mcp_client.post(
            "/api/v1/secrets",
            json={"name": "api-token", "type": "local", "entries": {"k": "tok-xyz"}},
        ),
        status=201,
    )
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={
                "name": "with-secret",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer ${secret:api-token/k}"},
            },
        ),
        status=201,
    )
    seen: dict[str, Any] = {}

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        seen["connection"] = connection
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    assert_ok(await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools"))
    assert seen["connection"] == HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "Bearer tok-xyz"}
    )


async def test_list_server_tools_missing_secret_returns_502(
    mcp_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dangling placeholder fails resolution without leaking the reason."""
    created = assert_ok(
        await mcp_client.post(
            "/api/v1/mcp-servers",
            json={
                "name": "dangling",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer ${secret:nope/k}"},
            },
        ),
        status=201,
    )
    connected: list[str] = []

    async def fake_list_server_tools(connection: McpConnection) -> list[Any]:
        connected.append(connection.label)
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    response = await mcp_client.get(f"/api/v1/mcp-servers/{created['id']}/tools")
    err = assert_err(response, code="SECRET_RESOLUTION_FAILED", status=502)
    assert err["details"] == {"secret": "nope"}
    assert connected == []


# ---------- python-lint ----------


async def _lint(mcp_client: AsyncClient, source: str) -> list[dict[str, Any]]:
    response = await mcp_client.post(
        "/api/v1/mcp-servers/python-lint", json={"source": source}
    )
    data: list[dict[str, Any]] = assert_ok(response)
    return data


async def test_python_lint_clean_script_has_no_diagnostics(
    mcp_client: AsyncClient,
) -> None:
    source = 'import json\n\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n'
    assert await _lint(mcp_client, source) == []


async def test_python_lint_reports_a_syntax_error_alone(
    mcp_client: AsyncClient,
) -> None:
    diagnostics = await _lint(mcp_client, "def f(x):\n    return (x\n")
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == "error"
    assert diagnostics[0]["line"] == 2
    assert diagnostics[0]["column"] == 11
    assert set(diagnostics[0]) >= {"endLine", "endColumn", "message"}


async def test_python_lint_warns_on_convention_slips(mcp_client: AsyncClient) -> None:
    diagnostics = await _lint(
        mcp_client, "import requests\n\ndef f(x):\n    return x\n"
    )
    by_message = {d["message"].split(" ")[0]: d for d in diagnostics}
    assert {d["severity"] for d in diagnostics} == {"warning"}
    assert by_message["'requests'"]["line"] == 1
    assert by_message["'f'"] == {
        "line": 3,
        "column": 0,
        "endLine": 3,
        "endColumn": 5,
        "severity": "warning",
        "message": "'f' has no docstring: the tool will have no description.",
    }
    assert (by_message["Parameter"]["line"], by_message["Parameter"]["column"]) == (
        3,
        6,
    )


async def test_python_lint_warns_when_no_tool_is_exposed(
    mcp_client: AsyncClient,
) -> None:
    diagnostics = await _lint(mcp_client, "def _helper() -> None:\n    pass\n")
    assert [d["message"] for d in diagnostics] == [
        "No public top-level function: this server exposes no tools."
    ]


async def test_python_lint_columns_count_characters(mcp_client: AsyncClient) -> None:
    source = 'def f(a: int, 名前, b: int) -> int:\n    """Doc."""\n    return a\n'
    [diagnostic] = await _lint(mcp_client, source)
    assert (diagnostic["column"], diagnostic["endColumn"]) == (14, 16)


async def test_python_lint_requires_the_developer_role(
    mcp_client: AsyncClient,
) -> None:
    response = await mcp_client.post(
        "/api/v1/mcp-servers/python-lint",
        json={"source": "x = 1"},
        headers={"X-User-Id": "carol", "X-User-Roles": ""},
    )
    assert_err(response, "FORBIDDEN", 403)
