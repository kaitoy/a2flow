"""Tests for where a proxied MCP operation is carried out.

The happy path of the remote executor needs a listener with real TLS material
and lives in ``test_mcp_proxy_app.py``. What is covered here is the choice
between the two executors, the local one's delegation, the shape that crosses
the wire, and how remote failures come back.
"""

from pathlib import Path
from typing import Any

import pytest
from mcp import types

from infrastructure import mcp_client
from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from infrastructure.mcp_executor import (
    LocalMcpExecutor,
    RemoteMcpExecutor,
    get_mcp_executor,
)
from models.mcp_execution import connection_to_spec, spec_to_connection
from repositories.exceptions import McpConnectionError


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> RemoteMcpExecutor:
    """A remote executor pointed at TLS material that does not exist.

    Enough to exercise everything that happens before a socket is opened.
    """
    monkeypatch.setenv("MCP_PROXY_TLS_DIR", str(tmp_path / "published"))
    monkeypatch.setenv("MCP_BACKEND_TLS_DIR", str(tmp_path / "private"))
    return RemoteMcpExecutor("https://mcp-proxy:8443")


# --------------------------------------------------------------------------
# Choosing an executor
# --------------------------------------------------------------------------


def test_operations_run_in_process_when_no_proxy_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default, so a local checkout and the test suite need one process."""
    monkeypatch.delenv("MCP_PROXY_URL", raising=False)

    assert isinstance(get_mcp_executor(), LocalMcpExecutor)


def test_setting_a_proxy_url_moves_operations_out_of_this_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_PROXY_URL", "https://mcp-proxy:8443")

    assert isinstance(get_mcp_executor(), RemoteMcpExecutor)


# --------------------------------------------------------------------------
# The local executor
# --------------------------------------------------------------------------


async def test_the_local_executor_lists_through_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[McpConnection] = []

    async def _list(connection: McpConnection) -> list[types.Tool]:
        seen.append(connection)
        return [types.Tool(name="read_file", inputSchema={})]

    monkeypatch.setattr(mcp_client, "list_server_tools", _list)
    connection = HttpConnection(url="https://mcp.example.com/mcp")

    tools = await LocalMcpExecutor().list_tools(connection)

    assert [tool.name for tool in tools] == ["read_file"]
    assert seen == [connection]


async def test_the_local_executor_ignores_the_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It authorizes the call, and authorization already happened upstream."""
    seen: list[tuple[str, dict[str, Any]]] = []

    async def _call(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        seen.append((tool_name, arguments))
        return types.CallToolResult(content=[])

    monkeypatch.setattr(mcp_client, "call_server_tool", _call)

    await LocalMcpExecutor().call_tool(
        HttpConnection(url="https://mcp.example.com/mcp"),
        "read_file",
        {"path": "/etc/hosts"},
        session_id="sess-1",
        credential=None,
    )

    assert seen == [("read_file", {"path": "/etc/hosts"})]


# --------------------------------------------------------------------------
# What crosses the wire
# --------------------------------------------------------------------------


def test_an_http_connection_survives_the_round_trip() -> None:
    connection = HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "Bearer resolved"}
    )

    assert spec_to_connection(connection_to_spec(connection)) == connection


def test_a_stdio_connection_survives_the_round_trip() -> None:
    """Including ``raw_args``, which is what keeps a resolved secret out of logs."""
    connection = StdioConnection(
        command="npx",
        args=["--token", "resolved"],
        env={"API_KEY": "resolved"},
        raw_args=["--token", "${env:API_KEY}"],
    )

    restored = spec_to_connection(connection_to_spec(connection))

    assert restored == connection
    assert restored.label == "npx --token ${env:API_KEY}"


def test_the_spec_carries_resolved_secrets_because_the_proxy_cannot_resolve_them() -> (
    None
):
    """The proxy holds neither the Fernet key nor a database; this is deliberate."""
    spec = connection_to_spec(
        StdioConnection(command="uvx", args=["pkg"], env={"API_KEY": "resolved"})
    )

    assert spec.model_dump(mode="json", by_alias=True)["env"] == {"API_KEY": "resolved"}


# --------------------------------------------------------------------------
# How remote failures come back
# --------------------------------------------------------------------------


async def test_missing_tls_material_is_reported_as_a_connection_error(
    remote: RemoteMcpExecutor,
) -> None:
    """Startup never provisioned it. A deployment fault, but not a crash."""
    with pytest.raises(McpConnectionError) as excinfo:
        await remote.list_tools(HttpConnection(url="https://mcp.example.com/mcp"))

    assert "TLS material" in excinfo.value.reason


async def test_a_remote_failure_uses_the_same_error_type_as_a_local_one(
    remote: RemoteMcpExecutor,
) -> None:
    """So the gateway's error handling does not care which executor it holds."""
    with pytest.raises(McpConnectionError):
        await remote.call_tool(
            StdioConnection(command="npx"),
            "read_file",
            {},
            session_id="sess-1",
            credential=None,
        )
