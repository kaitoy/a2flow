"""Thin client adapter for MCP servers, over streamable HTTP or stdio.

Wraps the ``mcp`` Python SDK so the rest of A2Flow never touches its connection
machinery directly. This is the module that actually reaches a third-party MCP
server, so it is the module that runs inside the MCP proxy container — reached
from the backend through :mod:`infrastructure.mcp_executor`.

Design notes:

* **Connection specs, not transports.** Callers build an :data:`McpConnection`
  once — normally via
  :func:`infrastructure.mcp_connection.resolve_connection`, which also expands
  ``${secret:NAME/KEY}`` placeholders — and hand it to :func:`list_server_tools` /
  :func:`call_server_tool`. Nothing outside this module branches on transport.
* **Nothing of A2Flow's own world.** Deliberately no ORM row, no session, no
  settings: resolution lives in :mod:`infrastructure.mcp_connection` precisely
  so this module's imports are the MCP SDK, httpx2, and two dependency-free
  modules of ours. What runs beside a user-registered MCP server should be as
  small as it can be.
* **One connection per operation.** Both ``streamable_http_client`` and
  ``stdio_client`` run an anyio task group that must be entered and exited in
  the same asyncio task; opening and closing the session inside a single
  ``async with`` stack per call guarantees that, at the cost of a handshake
  (for stdio: a process spawn) per tool call.
* **Two transports.** Streamable HTTP for remote servers; stdio for servers
  launched as a child process. SSE-transport servers are not supported in this
  version.
* **Elicitation, when the caller asks for it.** :func:`call_server_tool` takes
  an optional :data:`ElicitHandler`. Only then does the session advertise the
  elicitation capability, and the server may stop mid-call to ask a person
  something (``elicitation/create``). The operation's timeout is paused for as
  long as the handler takes -- it is waiting on a human, not on the server --
  so the handler must bound that wait itself.
* Any connection, protocol, or timeout failure is normalized to
  :class:`repositories.exceptions.McpConnectionError` so callers map it to one
  error shape (HTTP 502 for the API, an ``{"error": ...}`` dict for the agent).
  Its ``reason`` — and a matching warning logged right here — comes from
  :func:`_describe_failure`, not a bare ``str()``: both transports run inside
  an anyio task group, so the SDK often raises a
  ``BaseExceptionGroup("unhandled errors in a TaskGroup", [...])`` whose own
  ``str()`` hides the real cause behind "(1 sub-exception)".
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.context import ClientRequestContext
from mcp.client.session import ElicitationFnT
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._stream_protocols import ReadStream, WriteStream
from mcp.shared.message import SessionMessage

from infrastructure.url_safety import assert_public_http_url, guard_peer_address
from repositories.exceptions import McpConnectionError

logger = logging.getLogger(__name__)

#: Upper bound, in seconds, for one whole streamable-HTTP MCP operation
#: (connect + initialize + the list/call round-trip).
MCP_TIMEOUT_SECONDS = 30.0

#: Upper bound, in seconds, for one whole stdio MCP operation. Larger than the
#: HTTP budget because the first run of a package-launcher command such as
#: ``npx -y pkg@version`` or ``uvx pkg`` downloads the package before the
#: server process even starts, which routinely outlasts 30 seconds.
MCP_STDIO_TIMEOUT_SECONDS = 120.0

#: Answers one ``elicitation/create`` request a server sends while a tool call
#: is in flight. It receives the request's parameters (a form or a URL request)
#: and returns the person's answer. It may take minutes; it is expected to
#: bound that wait itself and answer ``cancel`` when it gives up.
ElicitHandler = Callable[[types.ElicitRequestParams], Awaitable[types.ElicitResult]]

_ReadStream = ReadStream[SessionMessage | Exception]
_WriteStream = WriteStream[SessionMessage]

#: Per-request HTTP timeouts for streamable-HTTP sessions, matching the SDK's
#: own defaults: a long read timeout because a server may hold a response
#: stream open. The whole operation is still bounded by ``MCP_TIMEOUT_SECONDS``.
_HTTP_TIMEOUT = httpx2.Timeout(30.0, read=300.0)


@dataclass(frozen=True)
class HttpConnection:
    """A remote MCP server reachable over streamable HTTP.

    Attributes:
        url: The server's streamable HTTP endpoint.
        headers: Extra HTTP headers sent with every request, with any
            ``${secret:NAME/KEY}`` placeholders already resolved.
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
        command: The executable to run: ``npx`` or ``uvx``, or -- for a
            ``script`` server -- the interpreter that starts its runner.
        args: ``argv`` entries passed to the executable, with any
            ``${env:NAME}`` placeholders already expanded against ``env``.
            Handed to the SDK as a list and spawned without a shell, so
            nothing here is word-split or interpreted by a shell.
        env: Environment variables merged over the small safe-to-inherit set
            :func:`mcp.client.stdio.get_default_environment` provides, with any
            ``${secret:NAME/KEY}`` placeholders already resolved. The launching
            process's own environment is *not* inherited.
        raw_args: ``args`` before ``${env:NAME}`` expansion — used only for
            :attr:`label`, so an expanded value that came from a secret-backed
            ``env`` entry never appears in an error message or log line.
            Falls back to ``args`` when omitted (e.g. by tests constructing a
            connection directly).
    """

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    raw_args: list[str] | None = field(default=None, compare=False)

    @property
    def label(self) -> str:
        """Short identification of this server for error messages and logs.

        Deliberately excludes ``env``, whose values may hold resolved
        secrets — and uses ``raw_args`` rather than ``args`` for the same
        reason, since an ``args`` entry may itself have been expanded from a
        secret-backed ``env`` value.
        """
        display_args = self.raw_args if self.raw_args is not None else self.args
        return " ".join([self.command, *display_args])

    @property
    def timeout_seconds(self) -> float:
        """Upper bound, in seconds, for one whole operation on this connection."""
        return MCP_STDIO_TIMEOUT_SECONDS


#: Everything needed to open a session against one registered MCP server.
McpConnection = HttpConnection | StdioConnection


def _create_http_client(headers: dict[str, str]) -> httpx2.AsyncClient:
    """Build the HTTP client a streamable-HTTP MCP session runs on.

    Redirects need no handling here: the SDK follows one only when it stays on
    the endpoint's origin and keeps the request method, whatever the client's
    own ``follow_redirects`` says, so a server URL that passed host validation
    cannot bounce a request to a private/internal address.

    Every new connection's peer address is checked by
    :func:`~infrastructure.url_safety.guard_peer_address`, so a hostname that
    passed validation but now resolves to an internal address (DNS rebinding)
    is refused before any request bytes are sent.

    Args:
        headers: Extra headers to send with every request.

    Returns:
        A configured ``httpx2.AsyncClient``; the caller closes it.
    """
    return httpx2.AsyncClient(
        headers=headers,
        timeout=_HTTP_TIMEOUT,
        event_hooks={"request": [guard_peer_address]},
    )


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
            whose host resolves to an address that is not globally routable,
            or is multicast. Rechecked here (in addition to the
            ``HttpUrl`` Pydantic validation at API-input time) against rows
            that bypass Pydantic; DNS rebinding is caught at connect time by
            the client from :func:`_create_http_client`, surfacing as a
            connection failure. Not applicable to stdio, which opens no
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
    async with (
        _create_http_client(connection.headers) as http_client,
        streamable_http_client(connection.url, http_client=http_client) as (
            read_stream,
            write_stream,
        ),
    ):
        yield read_stream, write_stream


@asynccontextmanager
async def mcp_session(
    connection: McpConnection, *, on_elicit: ElicitationFnT | None = None
) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP client session against a registered server.

    Args:
        connection: The server to connect to, with secrets already resolved.
        on_elicit: SDK-shaped callback answering the server's
            ``elicitation/create`` requests. When given, the session advertises
            the elicitation capability during ``initialize``; when omitted, it
            does not, and the SDK refuses any such request.

    Yields:
        An initialized :class:`mcp.ClientSession`; the connection is closed
        (and, for stdio, the child process reaped) when the context exits.

    Raises:
        infrastructure.url_safety.UnsafeUrlError: See :func:`_transport_streams`.
    """
    async with (
        _transport_streams(connection) as (read_stream, write_stream),
        ClientSession(
            read_stream, write_stream, elicitation_callback=on_elicit
        ) as session,
    ):
        await session.initialize()
        yield session


def _describe_failure(exc: BaseException) -> str:
    """Describe a connection failure, unwrapping any nested ``ExceptionGroup``.

    ``stdio_client`` and ``streamable_http_client`` both run their transport
    inside an anyio task group, so a connection failure often surfaces as a
    bare ``BaseExceptionGroup("unhandled errors in a TaskGroup", [...])``
    whose own ``str()`` is just "(1 sub-exception)" -- the actual cause is
    one level down, in ``.exceptions``.

    Args:
        exc: The exception caught around a connection attempt.

    Returns:
        The type and message of every leaf exception, recursing through
        nested groups and joined with ``"; "``.
    """
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe_failure(sub) for sub in exc.exceptions)
    return f"{type(exc).__name__}: {exc}"


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
        reason = _describe_failure(e)
        logger.warning(
            "Connection to MCP server %s failed: %s", connection.label, reason
        )
        raise McpConnectionError(connection.label, reason) from e


def _pausing_timeout(
    timeout: asyncio.Timeout, handler: ElicitHandler
) -> ElicitationFnT:
    """Wrap ``handler`` so ``timeout`` stands still while it waits on a person.

    The operation's budget is meant for the server, not for whoever answers
    the server's question, so the deadline is lifted for the duration of the
    handler and put back afterwards with exactly the time that was left.

    Args:
        timeout: The ``asyncio.timeout`` guarding the whole operation.
        handler: The caller's elicitation handler.

    Returns:
        A callback in the shape :class:`mcp.ClientSession` expects.
    """

    async def callback(
        context: ClientRequestContext,
        params: types.ElicitRequestParams,
    ) -> types.ElicitResult | types.ErrorData:
        loop = asyncio.get_running_loop()
        deadline = timeout.when()
        remaining = None if deadline is None else max(deadline - loop.time(), 0.0)
        timeout.reschedule(None)
        try:
            return await handler(params)
        finally:
            timeout.reschedule(None if remaining is None else loop.time() + remaining)

    return callback


async def call_server_tool(
    connection: McpConnection,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    on_elicit: ElicitHandler | None = None,
) -> types.CallToolResult:
    """Invoke ``tool_name`` with ``arguments`` on the server behind ``connection``.

    Tool-level failures are *not* raised: they come back inside the returned
    :class:`mcp.types.CallToolResult` with ``is_error`` set, so the caller can
    relay them to the agent verbatim.

    Args:
        connection: The server to call.
        tool_name: Name of the tool to invoke.
        arguments: JSON-serializable arguments matching the tool's input schema.
        on_elicit: Answers the server's ``elicitation/create`` requests during
            the call. The connection's timeout budget is paused while it runs.
            Omit it to keep the elicitation capability unadvertised.

    Returns:
        The raw ``tools/call`` result.

    Raises:
        McpConnectionError: If the server cannot be reached or launched,
            rejects the handshake, or does not respond within the connection's
            timeout budget.
    """
    try:
        async with asyncio.timeout(connection.timeout_seconds) as timeout:
            callback = (
                None if on_elicit is None else _pausing_timeout(timeout, on_elicit)
            )
            async with mcp_session(connection, on_elicit=callback) as session:
                return await session.call_tool(tool_name, arguments=arguments)
    except Exception as e:
        reason = _describe_failure(e)
        logger.warning(
            "Connection to MCP server %s failed: %s", connection.label, reason
        )
        raise McpConnectionError(connection.label, reason) from e
