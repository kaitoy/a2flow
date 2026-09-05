"""Tests for turning a registered server row into a connection spec.

Split from ``test_mcp_client.py`` along the same line as the modules: this
covers resolution, which is a backend concern, while that file covers the
transport, which runs in the MCP proxy container.
"""

import pytest

from infrastructure.mcp_client import HttpConnection, StdioConnection
from infrastructure.mcp_connection import resolve_connection
from infrastructure.secret_resolver import SecretResolver
from models.mcp_server import MCPServer, McpTransport
from repositories.exceptions import McpConnectionError


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
