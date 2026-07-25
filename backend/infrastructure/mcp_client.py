"""Thin client adapter for MCP servers, over streamable HTTP or stdio.

Wraps the ``mcp`` Python SDK so the rest of the backend never touches its
connection machinery directly. Used by :meth:`services.mcp_server.MCPServerService.list_tools`
(admin tool catalog) and by the agent proxy tools in
:mod:`infrastructure.mcp_tools`.

Design notes:

* **Connection specs, not transports.** Callers build an :data:`McpConnection`
  once — normally via :func:`resolve_connection`, which also expands
  ``${secret:NAME}`` placeholders — and hand it to :func:`list_server_tools` /
  :func:`call_server_tool`. Nothing outside this module branches on transport.
* **One connection per operation.** Both ``streamablehttp_client`` and
  ``stdio_client`` run an anyio task group that must be entered and exited in
  the same asyncio task; opening and closing the session inside a single
  ``async with`` stack per call guarantees that, at the cost of a handshake
  (for stdio: a process spawn) per tool call.
* **Two transports.** Streamable HTTP for remote servers; stdio for servers
  launched as a child process of the backend. SSE-transport servers are not
  supported in this version.
* Any connection, protocol, or timeout failure is normalized to
  :class:`repositories.exceptions.McpConnectionError` so callers map it to one
  error shape (HTTP 502 for the API, an ``{"error": ...}`` dict for the agent).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.message import SessionMessage

from infrastructure.secret_resolver import SecretResolver
from infrastructure.url_safety import assert_public_http_url
from models.mcp_server import MCPServer, McpTransport
from repositories.exceptions import McpConnectionError

#: Upper bound, in seconds, for one whole streamable-HTTP MCP operation
#: (connect + initialize + the list/call round-trip).
MCP_TIMEOUT_SECONDS = 30.0

#: Upper bound, in seconds, for one whole stdio MCP operation. Larger than the
#: HTTP budget because the first run of a package-launcher command such as
#: ``npx -y pkg@version`` or ``uvx pkg`` downloads the package before the
#: server process even starts, which routinely outlasts 30 seconds.
MCP_STDIO_TIMEOUT_SECONDS = 120.0

_ReadStream = MemoryObjectReceiveStream[SessionMessage | Exception]
_WriteStream = MemoryObjectSendStream[SessionMessage]


@dataclass(frozen=True)
class HttpConnection:
    """A remote MCP server reachable over streamable HTTP.

    Attributes:
        url: The server's streamable HTTP endpoint.
        headers: Extra HTTP headers sent with every request, with any
            ``${secret:NAME}`` placeholders already resolved.
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Short identification of this server for error messages and logs."""
        return self.url

    @property
    def timeout_seconds(self) -> float:
        """Upper bound, in seconds, for one whole operation on this connection."""
        return MCP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class StdioConnection:
    """An MCP server launched as a child process speaking stdio.

    Attributes:
        command: The executable to run: ``npx`` or ``uvx``.
        args: ``argv`` entries passed to the executable. Handed to the SDK as a
            list and spawned without a shell, so nothing here is word-split or
            interpreted by a shell.
        env: Environment variables merged over the small safe-to-inherit set
            :func:`mcp.client.stdio.get_default_environment` provides, with any
            ``${secret:NAME}`` placeholders already resolved. The backend's own
            environment (API keys, ``DB_URL``, …) is *not* inherited.
    """

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Short identification of this server for error messages and logs.

        Deliberately excludes ``env``, whose values may hold resolved secrets.
        """
        return " ".join([self.command, *self.args])

    @property
    def timeout_seconds(self) -> float:
        """Upper bound, in seconds, for one whole operation on this connection."""
        return MCP_STDIO_TIMEOUT_SECONDS


#: Everything needed to open a session against one registered MCP server.
McpConnection = HttpConnection | StdioConnection


async def resolve_connection(
    server: MCPServer, resolver: SecretResolver
) -> McpConnection:
    """Build the connection spec for a registered server, resolving its secrets.

    Args:
        server: The registered MCP server row.
        resolver: Resolver expanding ``${secret:NAME}`` placeholders in the
            server's header (remote) or environment (stdio) values.

    Returns:
        An :data:`McpConnection` ready to hand to :func:`list_server_tools` or
        :func:`call_server_tool`.

    Raises:
        McpConnectionError: If the row is missing the field its transport
            requires — only reachable for a row written outside the API, since
            both create and update validate the per-transport shape.
        repositories.exceptions.SecretResolutionError: If a referenced secret
            cannot be resolved.
    """
    if server.transport is McpTransport.stdio:
        if not server.command:
            raise McpConnectionError(server.name, "stdio server has no command")
        return StdioConnection(
            command=server.command,
            args=list(server.args),
            env=await resolver.resolve_mapping(server.env),
        )
    if not server.url:
        raise McpConnectionError(server.name, "streamable_http server has no url")
    return HttpConnection(
        url=server.url,
        headers=await resolver.resolve_mapping(server.headers),
    )


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
async def _transport_streams(
    connection: McpConnection,
) -> AsyncIterator[tuple[_ReadStream, _WriteStream]]:
    """Open the read/write stream pair for a connection's transport.

    Args:
        connection: The server to connect to.

    Yields:
        The transport's ``(read_stream, write_stream)`` pair; the underlying
        HTTP connection or child process is torn down when the context exits.

    Raises:
        infrastructure.url_safety.UnsafeUrlError: For a :class:`HttpConnection`
            whose host resolves to a loopback/private/link-local/reserved/
            multicast/unspecified address. Rechecked here (in addition to the
            ``HttpUrl`` Pydantic validation at API-input time) as
            defense-in-depth against DNS-rebinding-after-validation and rows
            that bypass Pydantic. Not applicable to stdio, which opens no
            socket.
    """
    if isinstance(connection, StdioConnection):
        parameters = StdioServerParameters(
            command=connection.command,
            args=list(connection.args),
            env=dict(connection.env),
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            yield read_stream, write_stream
        return

    await asyncio.to_thread(assert_public_http_url, connection.url)
    async with streamablehttp_client(
        connection.url,
        headers=connection.headers or None,
        httpx_client_factory=_create_no_redirect_http_client,
    ) as (read_stream, write_stream, _get_session_id):
        yield read_stream, write_stream


@asynccontextmanager
async def mcp_session(connection: McpConnection) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP client session against a registered server.

    Args:
        connection: The server to connect to, with secrets already resolved.

    Yields:
        An initialized :class:`mcp.ClientSession`; the connection is closed
        (and, for stdio, the child process reaped) when the context exits.

    Raises:
        infrastructure.url_safety.UnsafeUrlError: See :func:`_transport_streams`.
    """
    async with (
        _transport_streams(connection) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        yield session


async def list_server_tools(connection: McpConnection) -> list[types.Tool]:
    """Return the tools advertised by the MCP server behind ``connection``.

    Args:
        connection: The server to query.

    Returns:
        The server's tool list from a single ``tools/list`` round-trip.

    Raises:
        McpConnectionError: If the server cannot be reached or launched,
            rejects the handshake, or does not respond within the connection's
            timeout budget.
    """
    try:
        async with asyncio.timeout(connection.timeout_seconds):
            async with mcp_session(connection) as session:
                result = await session.list_tools()
                return list(result.tools)
    except Exception as e:
        raise McpConnectionError(connection.label, str(e)) from e


async def call_server_tool(
    connection: McpConnection,
    tool_name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    """Invoke ``tool_name`` with ``arguments`` on the server behind ``connection``.

    Tool-level failures are *not* raised: they come back inside the returned
    :class:`mcp.types.CallToolResult` with ``isError`` set, so the caller can
    relay them to the agent verbatim.

    Args:
        connection: The server to call.
        tool_name: Name of the tool to invoke.
        arguments: JSON-serializable arguments matching the tool's input schema.

    Returns:
        The raw ``tools/call`` result.

    Raises:
        McpConnectionError: If the server cannot be reached or launched,
            rejects the handshake, or does not respond within the connection's
            timeout budget.
    """
    try:
        async with asyncio.timeout(connection.timeout_seconds):
            async with mcp_session(connection) as session:
                return await session.call_tool(tool_name, arguments=arguments)
    except Exception as e:
        raise McpConnectionError(connection.label, str(e)) from e
