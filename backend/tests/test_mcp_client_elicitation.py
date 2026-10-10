"""Tests for answering a server's mid-call questions in ``infrastructure.mcp_client``.

A real FastMCP server is wired to the client over in-memory streams, replacing
only :func:`infrastructure.mcp_client._transport_streams`, so the
``elicitation/create`` round trip -- the capability advertised at
``initialize``, the request, the answer the tool sees -- is the SDK's own.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
import pytest
from mcp import types
from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.memory import create_client_server_memory_streams
from pydantic import BaseModel

from infrastructure import mcp_client
from infrastructure.mcp_client import HttpConnection
from repositories.exceptions import McpConnectionError

CONNECTION = HttpConnection(url="https://mcp.example.com/mcp")


class _Decision(BaseModel):
    """What the fake server asks for."""

    decision: str


def _server() -> FastMCP:
    """A server with one tool that asks before acting and one that is just slow."""
    server = FastMCP("elicitation-test")

    @server.tool()
    async def guarded(ctx: Context) -> str:  # type: ignore[type-arg]
        answer = await ctx.elicit("Do you want to continue?", _Decision)
        if answer.action == "accept":
            return f"accepted:{answer.data.decision}"
        return answer.action

    @server.tool()
    async def slow() -> str:
        await asyncio.sleep(1.0)
        return "done"

    return server


@pytest.fixture
def in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route every connection to a fresh in-memory FastMCP server."""

    @asynccontextmanager
    async def _streams(connection: Any) -> AsyncIterator[Any]:
        server = _server()._mcp_server
        async with (
            create_client_server_memory_streams() as (client_streams, server_streams),
            anyio.create_task_group() as group,
        ):
            group.start_soon(
                lambda: server.run(
                    server_streams[0],
                    server_streams[1],
                    server.create_initialization_options(),
                )
            )
            try:
                yield client_streams
            finally:
                group.cancel_scope.cancel()

    monkeypatch.setattr(mcp_client, "_transport_streams", _streams)


def _text(result: types.CallToolResult) -> str:
    """Return the first text block of a tool result."""
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


async def test_the_handler_answers_the_servers_question(in_memory: None) -> None:
    asked: list[str] = []

    async def answer(params: types.ElicitRequestParams) -> types.ElicitResult:
        asked.append(params.message)
        return types.ElicitResult(action="accept", content={"decision": "go"})

    result = await mcp_client.call_server_tool(
        CONNECTION, "guarded", {}, on_elicit=answer
    )

    assert asked == ["Do you want to continue?"]
    assert _text(result) == "accepted:go"


async def test_a_decline_reaches_the_tool(in_memory: None) -> None:
    async def answer(params: types.ElicitRequestParams) -> types.ElicitResult:
        return types.ElicitResult(action="decline")

    result = await mcp_client.call_server_tool(
        CONNECTION, "guarded", {}, on_elicit=answer
    )

    assert _text(result) == "decline"


async def test_without_a_handler_the_server_cannot_ask(in_memory: None) -> None:
    """No capability is advertised, so the SDK refuses the request."""
    result = await mcp_client.call_server_tool(CONNECTION, "guarded", {})

    assert result.isError
    assert "Elicitation not supported" in _text(result)


async def test_the_timeout_stands_still_while_a_person_answers(
    in_memory: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The budget is for the server; the answer takes longer than all of it."""
    monkeypatch.setattr(mcp_client, "MCP_TIMEOUT_SECONDS", 0.5)

    async def answer(params: types.ElicitRequestParams) -> types.ElicitResult:
        await asyncio.sleep(1.0)
        return types.ElicitResult(action="accept", content={"decision": "late"})

    result = await mcp_client.call_server_tool(
        CONNECTION, "guarded", {}, on_elicit=answer
    )

    assert _text(result) == "accepted:late"


async def test_the_timeout_still_bounds_the_server_itself(
    in_memory: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pausing only covers the wait on a person, never a slow server."""
    monkeypatch.setattr(mcp_client, "MCP_TIMEOUT_SECONDS", 0.5)

    async def answer(params: types.ElicitRequestParams) -> types.ElicitResult:
        return types.ElicitResult(action="decline")

    with pytest.raises(McpConnectionError):
        await mcp_client.call_server_tool(CONNECTION, "slow", {}, on_elicit=answer)
