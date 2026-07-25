"""Tests for MCP registry search: parsing/filtering and the HTTP endpoint."""

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from infrastructure import mcp_registry_client
from models.mcp_registry import McpRegistrySearchResult, McpRegistryServerEntry
from models.mcp_server import McpTransport
from models.user import SYSTEM_USER_ID
from repositories.exceptions import RegistryUnavailableError
from tests._envelope import assert_err, assert_ok
from tests.conftest import _install_auth_overrides


class _FakeResponse:
    """Minimal stand-in for an ``httpx.Response`` returned by the fake client."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Async-context-manager stand-in for ``httpx.AsyncClient``.

    Captures the query params of the last ``get`` call and returns a canned
    payload, or raises a canned exception.
    """

    def __init__(self, payload: dict[str, Any] | None, exc: Exception | None) -> None:
        self._payload = payload
        self._exc = exc
        self.last_params: dict[str, str] | None = None

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def get(
        self, url: str, params: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.last_params = params
        if self._exc is not None:
            raise self._exc
        assert self._payload is not None
        return _FakeResponse(self._payload)


def _payload() -> dict[str, Any]:
    """Return a registry list payload mixing registrable and skippable servers."""
    return {
        "servers": [
            {
                "server": {
                    "name": "io.example/weather",
                    "title": "Weather",
                    "description": "Weather lookups.",
                    "version": "1.2.0",
                    "repository": {"url": "https://github.com/example/weather"},
                    "remotes": [
                        {
                            "type": "streamable-http",
                            "url": "https://mcp.example.com/weather",
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "description": "API token",
                                    "isRequired": True,
                                    "isSecret": True,
                                }
                            ],
                        }
                    ],
                },
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {"status": "active"}
                },
            },
            {
                # npm stdio package -> registrable over stdio
                "server": {
                    "name": "io.example/local-only",
                    "version": "0.1.0",
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "local-only",
                            "version": "0.1.0",
                            "runtimeHint": "npx",
                            "transport": {"type": "stdio"},
                            "runtimeArguments": [{"type": "positional", "value": "-y"}],
                            "packageArguments": [
                                {"type": "named", "name": "--root", "value": "/data"},
                                {"type": "named", "name": "--verbose"},
                            ],
                            "environmentVariables": [
                                {
                                    "name": "API_KEY",
                                    "description": "Token",
                                    "isRequired": True,
                                    "isSecret": True,
                                },
                                {"name": "ROOT", "default": "/data"},
                            ],
                        }
                    ],
                },
                "_meta": {},
            },
            {
                # OCI package -> skipped (the backend image cannot launch it)
                "server": {
                    "name": "io.example/oci-only",
                    "version": "2.0.0",
                    "packages": [
                        {
                            "registryType": "oci",
                            "identifier": "example/mcp",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {},
            },
            {
                # sse-only remote, no packages -> skipped entirely
                "server": {
                    "name": "io.example/sse",
                    "version": "1.0.0",
                    "remotes": [{"type": "sse", "url": "https://mcp.example.com/sse"}],
                },
                "_meta": {},
            },
        ],
        "metadata": {"count": 4, "nextCursor": "next-page-token"},
    }


@pytest.mark.asyncio
async def test_search_surfaces_streamable_http_remotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(payload=_payload(), exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers(search="weather")

    assert isinstance(result, McpRegistrySearchResult)
    assert result.next_cursor == "next-page-token"

    entry = result.servers[0]
    assert entry.name == "io.example/weather"
    assert entry.transport is McpTransport.streamable_http
    assert entry.url == "https://mcp.example.com/weather"
    assert entry.title == "Weather"
    assert entry.status == "active"
    assert entry.repository_url == "https://github.com/example/weather"
    assert len(entry.headers) == 1
    header = entry.headers[0]
    assert header.name == "Authorization"
    assert header.is_required is True
    assert header.is_secret is True


@pytest.mark.asyncio
async def test_search_surfaces_launchable_stdio_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(payload=_payload(), exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers()

    entry = next(s for s in result.servers if s.name == "io.example/local-only")
    assert entry.transport is McpTransport.stdio
    assert entry.command == "npx"
    assert entry.args == ["-y", "local-only@0.1.0", "--root", "/data", "--verbose"]
    assert entry.url is None
    assert [(v.name, v.value, v.is_secret) for v in entry.env] == [
        ("API_KEY", None, True),
        ("ROOT", "/data", False),
    ]


@pytest.mark.asyncio
async def test_search_skips_servers_it_cannot_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OCI packages and SSE-only remotes have no launchable form here."""
    fake = _FakeClient(payload=_payload(), exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers()

    assert [s.name for s in result.servers] == [
        "io.example/weather",
        "io.example/local-only",
    ]


@pytest.mark.asyncio
async def test_search_prefers_the_remote_when_a_server_has_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "servers": [
            {
                "server": {
                    "name": "io.example/both",
                    "version": "1.0.0",
                    "remotes": [
                        {"type": "streamable-http", "url": "https://both.example/mcp"}
                    ],
                    "packages": [
                        {
                            "registryType": "pypi",
                            "identifier": "both-mcp",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {},
            }
        ],
        "metadata": {},
    }
    fake = _FakeClient(payload=payload, exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers()

    assert len(result.servers) == 1
    assert result.servers[0].transport is McpTransport.streamable_http


@pytest.mark.asyncio
async def test_search_defaults_the_command_from_the_package_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PyPI package without a runtimeHint is launched with uvx."""
    payload = {
        "servers": [
            {
                "server": {
                    "name": "io.example/pypi",
                    "version": "0.2.0",
                    "packages": [
                        {
                            "registryType": "pypi",
                            "identifier": "pypi-mcp",
                            "version": "0.2.0",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {},
            }
        ],
        "metadata": {},
    }
    fake = _FakeClient(payload=payload, exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    entry = (await mcp_registry_client.search_servers()).servers[0]
    assert entry.command == "uvx"
    assert entry.args == ["pypi-mcp@0.2.0"]


@pytest.mark.asyncio
async def test_search_skips_a_package_with_an_unsupported_runtime_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runtimeHint other than npx/uvx has no launchable form here."""
    payload = {
        "servers": [
            {
                "server": {
                    "name": "io.example/bunx-only",
                    "version": "0.1.0",
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "bunx-mcp",
                            "version": "0.1.0",
                            "runtimeHint": "bunx",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {},
            }
        ],
        "metadata": {},
    }
    fake = _FakeClient(payload=payload, exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers()

    assert result.servers == []


@pytest.mark.asyncio
async def test_search_passes_search_and_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(payload={"servers": [], "metadata": {}}, exc=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    result = await mcp_registry_client.search_servers(search="github", cursor="abc")

    assert result.servers == []
    assert result.next_cursor is None
    assert fake.last_params is not None
    assert fake.last_params["search"] == "github"
    assert fake.last_params["cursor"] == "abc"
    assert fake.last_params["version"] == "latest"


@pytest.mark.asyncio
async def test_search_raises_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeClient(payload=None, exc=RuntimeError("connection refused"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: fake)

    with pytest.raises(RegistryUnavailableError):
        await mcp_registry_client.search_servers(search="x")


@pytest_asyncio.fixture()
async def registry_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient bound to the app with auth overridden (no DB needed)."""
    from main import app

    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_endpoint_returns_envelope(
    registry_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(
        search: str | None = None, cursor: str | None = None
    ) -> McpRegistrySearchResult:
        return McpRegistrySearchResult(
            servers=[
                McpRegistryServerEntry(
                    name="io.example/weather",
                    title="Weather",
                    version="1.2.0",
                    url="https://mcp.example.com/weather",
                )
            ],
            next_cursor="more",
        )

    monkeypatch.setattr(mcp_registry_client, "search_servers", fake_search)

    data = assert_ok(await registry_client.get("/api/v1/mcp-registry?search=weather"))
    assert data["nextCursor"] == "more"
    assert data["servers"][0]["url"] == "https://mcp.example.com/weather"


@pytest.mark.asyncio
async def test_search_endpoint_502_on_registry_error(
    registry_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_search(
        search: str | None = None, cursor: str | None = None
    ) -> McpRegistrySearchResult:
        raise RegistryUnavailableError("connection refused")

    monkeypatch.setattr(mcp_registry_client, "search_servers", fake_search)

    response = await registry_client.get("/api/v1/mcp-registry")
    err = assert_err(response, code="REGISTRY_UNREACHABLE", status=502)
    assert err["message"] == "MCP registry unavailable"
    assert err["details"] is None
    assert "connection refused" not in response.text
