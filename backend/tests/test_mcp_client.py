"""Tests for the SSRF guards in ``infrastructure.mcp_client``.

The autouse ``_fake_dns_resolution`` fixture in ``conftest.py`` makes every
hostname resolve to a public IP by default; these tests override it per-test
to prove the pre-connection recheck in ``mcp_session`` independently blocks a
URL whose host resolves to a disallowed address — including for data that
bypassed the ``HttpUrl`` Pydantic validation entirely (e.g. a row written
directly to the database).
"""

import pytest

from infrastructure.mcp_client import (
    _create_no_redirect_http_client,
    call_server_tool,
    list_server_tools,
)
from repositories.exceptions import McpConnectionError


async def test_list_server_tools_rejects_url_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.0.0.5"]
    )
    with pytest.raises(McpConnectionError):
        await list_server_tools("http://internal.example.com/mcp")


async def test_call_server_tool_rejects_url_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "infrastructure.url_safety.resolve_host", lambda host: ["10.0.0.5"]
    )
    with pytest.raises(McpConnectionError):
        await call_server_tool("http://internal.example.com/mcp", None, "some_tool", {})


async def test_list_server_tools_rejects_loopback_literal() -> None:
    with pytest.raises(McpConnectionError):
        await list_server_tools("http://127.0.0.1/mcp")


async def test_create_no_redirect_http_client_disables_redirects() -> None:
    client = _create_no_redirect_http_client()
    try:
        assert client.follow_redirects is False
    finally:
        await client.aclose()
