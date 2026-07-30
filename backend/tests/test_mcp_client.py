"""Tests for connection dispatch and the SSRF guards in ``infrastructure.mcp_client``.

The autouse ``_fake_dns_resolution`` fixture in ``conftest.py`` makes every
hostname resolve to a public IP by default; the SSRF tests override it per-test
to prove the pre-connection recheck in ``mcp_session`` independently blocks a
URL whose host resolves to a disallowed address — including for data that
bypassed the ``HttpUrl`` Pydantic validation entirely (e.g. a row written
directly to the database). The stdio tests cover the other half of the
dispatch: that a stdio connection skips the URL check entirely and reports a
launch failure through the same error type.
"""

import pytest

from infrastructure.mcp_client import (
    MCP_STDIO_TIMEOUT_SECONDS,
    MCP_TIMEOUT_SECONDS,
    HttpConnection,
    StdioConnection,
    _create_no_redirect_http_client,
    call_server_tool,
    list_server_tools,
    resolve_connection,
)
from infrastructure.secret_resolver import SecretResolver
from models.mcp_server import MCPServer, McpTransport
from repositories.exceptions import McpConnectionError

_URL = "http://internal.example.com/mcp"


async def test_list_server_tools_rejects_url_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.0.0.5"]
    )
    with pytest.raises(McpConnectionError):
        await list_server_tools(HttpConnection(url=_URL))


async def test_call_server_tool_rejects_url_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.0.0.5"]
    )
    with pytest.raises(McpConnectionError):
        await call_server_tool(HttpConnection(url=_URL), "some_tool", {})


async def test_list_server_tools_rejects_loopback_literal() -> None:
    with pytest.raises(McpConnectionError):
        await list_server_tools(HttpConnection(url="http://127.0.0.1/mcp"))


async def test_stdio_connection_skips_the_url_safety_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stdio server opens no socket, so the SSRF guard must not run for it."""

    def _fail(host: str) -> list[str]:
        raise AssertionError("url safety must not be checked for a stdio connection")

    monkeypatch.setattr("infrastructure.url_safety.resolve_host", _fail)
    connection = StdioConnection(command="a2flow-no-such-command", args=["--version"])
    with pytest.raises(McpConnectionError):
        await list_server_tools(connection)


async def test_stdio_launch_failure_reports_command_without_env() -> None:
    connection = StdioConnection(
        command="a2flow-no-such-command",
        args=["--flag"],
        env={"API_KEY": "super-secret"},
    )
    with pytest.raises(McpConnectionError) as excinfo:
        await list_server_tools(connection)
    assert excinfo.value.server == "a2flow-no-such-command --flag"
    assert "super-secret" not in excinfo.value.server


def test_connection_timeouts_differ_by_transport() -> None:
    assert HttpConnection(url=_URL).timeout_seconds == MCP_TIMEOUT_SECONDS
    assert StdioConnection(command="npx").timeout_seconds == MCP_STDIO_TIMEOUT_SECONDS
    assert MCP_STDIO_TIMEOUT_SECONDS > MCP_TIMEOUT_SECONDS


class _StubResolver:
    """Stand-in for ``SecretResolver`` that upper-cases every value it sees."""

    async def resolve_mapping(self, values: dict[str, str]) -> dict[str, str]:
        return {key: value.upper() for key, value in values.items()}


def _server(**fields: object) -> MCPServer:
    defaults: dict[str, object] = {
        "id": "srv-1",
        "name": "srv",
        "tenant_id": "t-1",
        "created_by": "u-1",
        "updated_by": "u-1",
        "transport": McpTransport.streamable_http,
        "headers": {},
        "args": [],
        "env": {},
    }
    return MCPServer(**{**defaults, **fields})


def _unvalidated_server(**fields: object) -> MCPServer:
    """Build a stdio MCPServer bypassing pydantic validation.

    Used to simulate a row written outside the API (e.g. a stale
    ``${env:NAME}`` reference left over from an ``env`` key that was later
    removed), which ``MCPServerCreate``/``MCPServerService.update`` would
    otherwise reject before it ever reaches ``resolve_connection``.
    """
    defaults: dict[str, object] = {
        "id": "srv-1",
        "name": "srv",
        "tenant_id": "t-1",
        "created_by": "u-1",
        "updated_by": "u-1",
        "transport": McpTransport.stdio,
        "headers": {},
        "args": [],
        "env": {},
    }
    return MCPServer.model_construct(**{**defaults, **fields})  # type: ignore[arg-type]


async def test_resolve_connection_builds_http_connection_with_resolved_headers() -> (
    None
):
    resolver: SecretResolver = _StubResolver()  # type: ignore[assignment]
    connection = await resolve_connection(
        _server(url="https://mcp.example.com/mcp", headers={"Authorization": "token"}),
        resolver,
    )
    assert connection == HttpConnection(
        url="https://mcp.example.com/mcp", headers={"Authorization": "TOKEN"}
    )


async def test_resolve_connection_builds_stdio_connection_with_resolved_env() -> None:
    resolver: SecretResolver = _StubResolver()  # type: ignore[assignment]
    connection = await resolve_connection(
        _server(
            transport=McpTransport.stdio,
            command="npx",
            args=["-y", "pkg"],
            env={"API_KEY": "token"},
        ),
        resolver,
    )
    assert connection == StdioConnection(
        command="npx", args=["-y", "pkg"], env={"API_KEY": "TOKEN"}
    )


async def test_resolve_connection_rejects_a_row_missing_its_transport_field() -> None:
    resolver: SecretResolver = _StubResolver()  # type: ignore[assignment]
    with pytest.raises(McpConnectionError):
        await resolve_connection(_server(transport=McpTransport.stdio), resolver)
    with pytest.raises(McpConnectionError):
        await resolve_connection(_server(), resolver)


async def test_resolve_connection_expands_env_placeholder_in_args() -> None:
    """``${env:NAME}`` in args resolves to the (secret-resolved) env value,
    but the connection's label shows the placeholder, never the value."""
    resolver: SecretResolver = _StubResolver()  # type: ignore[assignment]
    connection = await resolve_connection(
        _server(
            transport=McpTransport.stdio,
            command="npx",
            args=["--token", "${env:API_KEY}"],
            env={"API_KEY": "token"},
        ),
        resolver,
    )
    assert connection == StdioConnection(
        command="npx", args=["--token", "TOKEN"], env={"API_KEY": "TOKEN"}
    )
    assert connection.label == "npx --token ${env:API_KEY}"
    assert "TOKEN" not in connection.label


async def test_resolve_connection_rejects_args_referencing_unknown_env_var() -> None:
    """A row written outside the API can carry a stale ``${env:NAME}`` reference."""
    resolver: SecretResolver = _StubResolver()  # type: ignore[assignment]
    server = _unvalidated_server(command="npx", args=["${env:MISSING}"], env={})
    with pytest.raises(McpConnectionError):
        await resolve_connection(server, resolver)


async def test_create_no_redirect_http_client_disables_redirects() -> None:
    client = _create_no_redirect_http_client()
    try:
        assert client.follow_redirects is False
    finally:
        await client.aclose()
