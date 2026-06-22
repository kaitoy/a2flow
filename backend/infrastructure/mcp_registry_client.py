"""HTTP client adapter for the official MCP registry.

Wraps the registry's REST API (``https://registry.modelcontextprotocol.io``) so
the rest of the backend never touches ``httpx`` or the registry's JSON shape
directly. Only servers exposing a streamable-HTTP remote are surfaced, because
A2Flow connects to remote MCP servers over streamable HTTP exclusively (see
:mod:`infrastructure.mcp_client`).

Any network, HTTP-status, or parse failure is normalized to
:class:`repositories.exceptions.RegistryUnavailableError` so callers map it to a
single error shape (HTTP 502).
"""

import os
from typing import Any

import httpx

from models.mcp_registry import (
    McpRegistryHeader,
    McpRegistrySearchResult,
    McpRegistryServerEntry,
)
from repositories.exceptions import RegistryUnavailableError

#: Base URL of the MCP registry; overridable via the ``MCP_REGISTRY_URL`` env var.
REGISTRY_BASE_URL = os.environ.get(
    "MCP_REGISTRY_URL", "https://registry.modelcontextprotocol.io"
)

#: Upper bound, in seconds, for a single registry round-trip.
REGISTRY_TIMEOUT_SECONDS = 10.0

#: Page size requested from the registry per search call.
_SEARCH_LIMIT = 50

#: The only remote transport type A2Flow can register.
_STREAMABLE_HTTP = "streamable-http"

#: Registry ``_meta`` key holding the official publication status of a server.
_OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"


def _streamable_remote(server: dict[str, Any]) -> dict[str, Any] | None:
    """Return the server's first streamable-HTTP remote, or ``None``.

    Args:
        server: A registry ``server`` object.

    Returns:
        The first remote whose ``type`` is ``streamable-http``, or ``None`` when
        the server has no streamable-HTTP remote.
    """
    for remote in server.get("remotes") or []:
        if isinstance(remote, dict) and remote.get("type") == _STREAMABLE_HTTP:
            return remote
    return None


def _to_entry(
    server: dict[str, Any], remote: dict[str, Any], status: str | None
) -> McpRegistryServerEntry:
    """Flatten a registry server and its streamable-HTTP remote into an entry.

    Args:
        server: The registry ``server`` object.
        remote: The server's streamable-HTTP remote (must carry a ``url``).
        status: The server's official publication status, if known.

    Returns:
        A :class:`McpRegistryServerEntry` carrying just the fields the admin UI
        needs to display the result and pre-fill the create form.
    """
    headers = [
        McpRegistryHeader(
            name=header["name"],
            description=header.get("description"),
            is_required=bool(header.get("isRequired", False)),
            is_secret=bool(header.get("isSecret", False)),
            value=header.get("value"),
        )
        for header in (remote.get("headers") or [])
        if header.get("name")
    ]
    repository = server.get("repository") or {}
    return McpRegistryServerEntry(
        name=server["name"],
        title=server.get("title"),
        description=server.get("description"),
        version=server.get("version", ""),
        status=status,
        url=remote["url"],
        headers=headers,
        website_url=server.get("websiteUrl"),
        repository_url=repository.get("url"),
    )


async def search_servers(
    search: str | None = None, cursor: str | None = None
) -> McpRegistrySearchResult:
    """Search the registry and return only streamable-HTTP servers.

    Requests the latest version of each server, keeps only those exposing a
    streamable-HTTP remote, and flattens each into a
    :class:`McpRegistryServerEntry`.

    Args:
        search: Substring matched against server names; ``None`` lists servers.
        cursor: Opaque pagination cursor from a previous result's
            ``next_cursor``; ``None`` fetches the first page.

    Returns:
        A page of registrable servers plus the cursor for the next page.

    Raises:
        RegistryUnavailableError: If the registry cannot be reached, returns an
            error status, or sends an unparseable body.
    """
    params: dict[str, str] = {"version": "latest", "limit": str(_SEARCH_LIMIT)}
    if search:
        params["search"] = search
    if cursor:
        params["cursor"] = cursor

    try:
        async with httpx.AsyncClient(timeout=REGISTRY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{REGISTRY_BASE_URL}/v0/servers", params=params
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except Exception as exc:
        raise RegistryUnavailableError(str(exc)) from exc

    entries: list[McpRegistryServerEntry] = []
    for item in payload.get("servers") or []:
        server = item.get("server") or {}
        remote = _streamable_remote(server)
        if remote is None or not remote.get("url") or not server.get("name"):
            continue
        official = (item.get("_meta") or {}).get(_OFFICIAL_META_KEY) or {}
        entries.append(_to_entry(server, remote, official.get("status")))

    next_cursor = (payload.get("metadata") or {}).get("nextCursor")
    return McpRegistrySearchResult(servers=entries, next_cursor=next_cursor)
