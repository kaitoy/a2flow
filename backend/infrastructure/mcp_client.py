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

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client

from infrastructure.url_safety import assert_public_http_url
from repositories.exceptions import McpConnectionError

#: Upper bound, in seconds, for one whole MCP operation (connect + initialize +
#: the list/call round-trip).
MCP_TIMEOUT_SECONDS = 30.0


def _create_no_redirect_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Build the httpx client MCP sessions use, with redirect-following disabled.

    The MCP SDK's own factory (``mcp.shared._httpx_utils.create_mcp_http_client``)
    hardcodes ``follow_redirects=True``. Without this override, a server URL
    that passed host validation could 30x-redirect a request to a
    private/internal address and the client would silently follow it. The
    streamable-HTTP MCP protocol has no legitimate need for redirects, so
    following them is simply turned off.

    Args:
        headers: Extra headers to send with every request.
        timeout: Request timeout; httpx's own default is applied if omitted.
        auth: Optional authentication handler.

    Returns:
        A configured, non-redirect-following ``httpx.AsyncClient``.
    """
    kwargs: dict[str, Any] = {"follow_redirects": False}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


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

    Raises:
        infrastructure.url_safety.UnsafeUrlError: If ``url``'s host resolves to
            a loopback/private/link-local/reserved/multicast/unspecified
            address. Rechecked here (in addition to the ``HttpUrl`` Pydantic
            validation at API-input time) as defense-in-depth against
            DNS-rebinding-after-validation and rows that bypass Pydantic.
    """
    await asyncio.to_thread(assert_public_http_url, url)
    async with (
        streamablehttp_client(
            url,
            headers=headers or None,
            httpx_client_factory=_create_no_redirect_http_client,
        ) as (
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
