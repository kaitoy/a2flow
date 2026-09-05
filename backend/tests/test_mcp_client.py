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
)
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


async def test_create_no_redirect_http_client_disables_redirects() -> None:
    client = _create_no_redirect_http_client()
    try:
        assert client.follow_redirects is False
    finally:
        await client.aclose()
