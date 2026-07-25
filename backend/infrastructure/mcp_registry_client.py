"""HTTP client adapter for the official MCP registry.

Wraps the registry's REST API (``https://registry.modelcontextprotocol.io``) so
the rest of the backend never touches ``httpx`` or the registry's JSON shape
directly. Each registry server is flattened into a single
:class:`models.mcp_registry.McpRegistryServerEntry` through whichever transport
A2Flow can use for it: its streamable-HTTP remote when it has one, otherwise one
of its stdio packages (see :mod:`infrastructure.mcp_client`).

The package-to-command mapping is deliberately best-effort — the registry
describes arguments declaratively and A2Flow renders them into a plain
``command`` plus ``argv`` list. The result only pre-fills a create form the
operator reviews before saving, so an imperfect rendering costs an edit rather
than a broken registration.

Any network, HTTP-status, or parse failure is normalized to
:class:`repositories.exceptions.RegistryUnavailableError` so callers map it to a
single error shape (HTTP 502).
"""

from typing import Any

import httpx

from config import get_settings
from models.mcp_registry import (
    McpRegistryEnvVar,
    McpRegistryHeader,
    McpRegistrySearchResult,
    McpRegistryServerEntry,
)
from models.mcp_server import McpTransport
from repositories.exceptions import RegistryUnavailableError

#: Base URL of the MCP registry; overridable via the ``MCP_REGISTRY_URL`` env var.
REGISTRY_BASE_URL = get_settings().mcp_registry_url

#: Upper bound, in seconds, for a single registry round-trip.
REGISTRY_TIMEOUT_SECONDS = 10.0

#: Page size requested from the registry per search call.
_SEARCH_LIMIT = 50

#: The only remote transport type A2Flow can register.
_STREAMABLE_HTTP = "streamable-http"

#: The package transport type A2Flow can register.
_STDIO = "stdio"

#: Package registries the backend image can launch, mapped to the command used
#: when the entry carries no ``runtimeHint``. ``oci``/``nuget``/``mcpb`` entries
#: are skipped rather than surfaced: nothing in the image can run them, so
#: offering them would only produce registrations that fail at connect time. A
#: package that does carry a ``runtimeHint`` naming anything other than
#: ``npx``/``uvx`` is skipped the same way, since the backend only accepts
#: those two commands (see :class:`models.mcp_server.McpCommand`).
_RUNTIME_BY_REGISTRY = {"npm": "npx", "pypi": "uvx"}

#: The only commands the backend accepts for a stdio server, per
#: :class:`models.mcp_server.McpCommand`.
_SUPPORTED_COMMANDS = {"npx", "uvx"}

#: Registry ``_meta`` key holding the official publication status of a server.
_OFFICIAL_META_KEY = "io.modelcontextprotocol.registry/official"


def _streamable_remote(server: dict[str, Any]) -> dict[str, Any] | None:
    """Return the server's first streamable-HTTP remote, or ``None``.

    Args:
        server: A registry ``server`` object.

    Returns:
        The first remote whose ``type`` is ``streamable-http`` and that carries
        a ``url``, or ``None`` when the server has no such remote.
    """
    for remote in server.get("remotes") or []:
        if not isinstance(remote, dict) or remote.get("type") != _STREAMABLE_HTTP:
            continue
        if remote.get("url"):
            return remote
    return None


def _stdio_package(server: dict[str, Any]) -> dict[str, Any] | None:
    """Return the server's first launchable stdio package, or ``None``.

    Args:
        server: A registry ``server`` object.

    Returns:
        The first stdio package published to a registry the backend image can
        launch (see :data:`_RUNTIME_BY_REGISTRY`), whose ``runtimeHint`` (if
        any) also names a supported command, or ``None``.
    """
    for package in server.get("packages") or []:
        if not isinstance(package, dict):
            continue
        transport = package.get("transport")
        if not isinstance(transport, dict) or transport.get("type") != _STDIO:
            continue
        if package.get("registryType") not in _RUNTIME_BY_REGISTRY:
            continue
        runtime_hint = package.get("runtimeHint")
        if runtime_hint and runtime_hint not in _SUPPORTED_COMMANDS:
            continue
        if package.get("identifier"):
            return package
    return None


def _render_argument(argument: dict[str, Any]) -> list[str]:
    """Render one declarative registry argument into ``argv`` entries.

    Args:
        argument: A registry ``runtimeArguments``/``packageArguments`` entry.

    Returns:
        Zero or more ``argv`` entries: a named argument yields its flag plus
        the concrete value when the registry supplies one, a positional
        argument yields just the value. An argument with neither a ``value``
        nor a ``default`` (typically one the operator must supply) yields only
        its flag, or nothing at all when positional.
    """
    value = argument.get("value") or argument.get("default")
    if argument.get("type") == "named":
        name = argument.get("name")
        if not name:
            return []
        return [name, value] if value else [name]
    return [value] if value else []


def _render_arguments(arguments: Any) -> list[str]:
    """Render a list of declarative registry arguments into ``argv`` entries.

    Args:
        arguments: The raw ``runtimeArguments``/``packageArguments`` list, which
            the registry may omit entirely.

    Returns:
        The concatenated rendering of every well-formed entry.
    """
    rendered: list[str] = []
    for argument in arguments or []:
        if isinstance(argument, dict):
            rendered.extend(_render_argument(argument))
    return rendered


def _package_command(package: dict[str, Any]) -> tuple[str, list[str]]:
    """Derive the command line that launches a stdio package.

    Args:
        package: A stdio package entry, already known to carry an
            ``identifier`` and a launchable ``registryType``.

    Returns:
        The ``(command, args)`` pair, where ``args`` is the package's runtime
        arguments, then the versioned package reference (``name@version``, the
        form both ``npx`` and ``uvx`` accept), then its package arguments.
    """
    registry_type = str(package["registryType"])
    command = str(package.get("runtimeHint") or _RUNTIME_BY_REGISTRY[registry_type])
    reference = str(package["identifier"])
    version = package.get("version")
    if version:
        reference = f"{reference}@{version}"
    args = [
        *_render_arguments(package.get("runtimeArguments")),
        reference,
        *_render_arguments(package.get("packageArguments")),
    ]
    return command, args


def _common_fields(server: dict[str, Any], status: str | None) -> dict[str, Any]:
    """Extract the transport-independent entry fields from a registry server.

    Args:
        server: The registry ``server`` object.
        status: The server's official publication status, if known.

    Returns:
        The keyword arguments shared by every :class:`McpRegistryServerEntry`.
    """
    repository = server.get("repository") or {}
    return {
        "name": server["name"],
        "title": server.get("title"),
        "description": server.get("description"),
        "version": server.get("version", ""),
        "status": status,
        "website_url": server.get("websiteUrl"),
        "repository_url": repository.get("url"),
    }


def _to_remote_entry(
    server: dict[str, Any], remote: dict[str, Any], status: str | None
) -> McpRegistryServerEntry:
    """Flatten a registry server and its streamable-HTTP remote into an entry.

    Args:
        server: The registry ``server`` object.
        remote: The server's streamable-HTTP remote (must carry a ``url``).
        status: The server's official publication status, if known.

    Returns:
        A ``streamable_http`` :class:`McpRegistryServerEntry`.
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
    return McpRegistryServerEntry(
        **_common_fields(server, status),
        transport=McpTransport.streamable_http,
        url=remote["url"],
        headers=headers,
    )


def _to_package_entry(
    server: dict[str, Any], package: dict[str, Any], status: str | None
) -> McpRegistryServerEntry:
    """Flatten a registry server and one of its stdio packages into an entry.

    Args:
        server: The registry ``server`` object.
        package: The server's launchable stdio package.
        status: The server's official publication status, if known.

    Returns:
        A ``stdio`` :class:`McpRegistryServerEntry`.
    """
    command, args = _package_command(package)
    env = [
        McpRegistryEnvVar(
            name=variable["name"],
            description=variable.get("description"),
            is_required=bool(variable.get("isRequired", False)),
            is_secret=bool(variable.get("isSecret", False)),
            value=variable.get("value") or variable.get("default"),
        )
        for variable in (package.get("environmentVariables") or [])
        if isinstance(variable, dict) and variable.get("name")
    ]
    return McpRegistryServerEntry(
        **_common_fields(server, status),
        transport=McpTransport.stdio,
        command=command,
        args=args,
        env=env,
    )


async def search_servers(
    search: str | None = None, cursor: str | None = None
) -> McpRegistrySearchResult:
    """Search the registry and return only servers A2Flow can register.

    Requests the latest version of each server and flattens it into a
    :class:`McpRegistryServerEntry` through its streamable-HTTP remote, falling
    back to a launchable stdio package. Servers offering neither are skipped.

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
        if not server.get("name"):
            continue
        official = (item.get("_meta") or {}).get(_OFFICIAL_META_KEY) or {}
        status = official.get("status")
        remote = _streamable_remote(server)
        if remote is not None:
            entries.append(_to_remote_entry(server, remote, status))
            continue
        package = _stdio_package(server)
        if package is not None:
            entries.append(_to_package_entry(server, package, status))

    next_cursor = (payload.get("metadata") or {}).get("nextCursor")
    return McpRegistrySearchResult(servers=entries, next_cursor=next_cursor)
