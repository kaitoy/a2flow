"""Thin client adapter for remote MCP servers over streamable HTTP.

Wraps the ``mcp`` Python SDK so the rest of the backend never touches its
connection machinery directly. Used by :meth:`services.mcp_server.MCPServerService.list_tools`
(admin tool catalog) and by the agent proxy tools in
:mod:`infrastructure.mcp_tools`.

Design notes:

* **One connection per operation.** ``streamablehttp_client`` runs an anyio task
  group that must be entered and exited in the same asyncio task; opening and
  closing the session inside a single ``async with`` stack per call guarantees
  that, at the cost of a connection handshake per tool call.
* **Streamable HTTP only.** SSE-transport servers are not supported in this
  version.
* Any connection, protocol, or timeout failure is normalized to
  :class:`repositories.exceptions.McpConnectionError` so callers map it to one
  error shape (HTTP 502 for the API, an ``{"error": ...}`` dict for the agent).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client

from repositories.exceptions import McpConnectionError

#: Upper bound, in seconds, for one whole MCP operation (connect + initialize +
#: the list/call round-trip).
MCP_TIMEOUT_SECONDS = 30.0


@asynccontextmanager
async def mcp_session(
    url: str, headers: dict[str, str] | None = None
) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP client session against a streamable HTTP server.

    Args:
        url: The server's streamable HTTP endpoint.
        headers: Extra HTTP headers (e.g. ``{"Authorization": "Bearer ..."}``)
            sent with every request; ``None`` or empty sends no extra headers.

    Yields:
        An initialized :class:`mcp.ClientSession`; the connection is closed when
        the context exits.
    """
    async with (
        streamablehttp_client(url, headers=headers or None) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        yield session


async def list_server_tools(
    url: str, headers: dict[str, str] | None = None
) -> list[types.Tool]:
    """Return the tools advertised by the MCP server at ``url``.

    Args:
        url: The server's streamable HTTP endpoint.
        headers: Extra HTTP headers sent with every request.

    Returns:
        The server's tool list from a single ``tools/list`` round-trip.

    Raises:
        McpConnectionError: If the server cannot be reached, rejects the
            handshake, or does not respond within :data:`MCP_TIMEOUT_SECONDS`.
    """
    try:
        async with asyncio.timeout(MCP_TIMEOUT_SECONDS):
            async with mcp_session(url, headers) as session:
                result = await session.list_tools()
                return list(result.tools)
    except Exception as e:
        raise McpConnectionError(url, str(e)) from e


async def call_server_tool(
    url: str,
    headers: dict[str, str] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    """Invoke ``tool_name`` with ``arguments`` on the MCP server at ``url``.

    Tool-level failures are *not* raised: they come back inside the returned
    :class:`mcp.types.CallToolResult` with ``isError`` set, so the caller can
    relay them to the agent verbatim.

    Args:
        url: The server's streamable HTTP endpoint.
        headers: Extra HTTP headers sent with every request.
        tool_name: Name of the tool to invoke.
        arguments: JSON-serializable arguments matching the tool's input schema.

    Returns:
        The raw ``tools/call`` result.

    Raises:
        McpConnectionError: If the server cannot be reached, rejects the
            handshake, or does not respond within :data:`MCP_TIMEOUT_SECONDS`.
    """
    try:
        async with asyncio.timeout(MCP_TIMEOUT_SECONDS):
            async with mcp_session(url, headers) as session:
                return await session.call_tool(tool_name, arguments=arguments)
    except Exception as e:
        raise McpConnectionError(url, str(e)) from e
