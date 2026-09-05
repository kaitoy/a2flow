"""Turning a registered MCP server row into a connection spec.

The half of talking to an MCP server that needs A2Flow's own world: the
``mcp_servers`` row, the ``${secret:NAME/KEY}`` placeholders in its headers or
environment, and the resolver that expands them. What comes out is an
:data:`infrastructure.mcp_client.McpConnection` -- a plain value carrying
everything the transport needs and nothing it does not.

**Why this is not in** :mod:`infrastructure.mcp_client`. That module is the
transport, and the transport is what runs in the MCP proxy container. It has no
business knowing what an ``MCPServer`` is, and a sandbox meant to hold as
little as possible should not be pulling in the ORM to find out. Keeping
resolution here leaves ``mcp_client`` depending on the MCP SDK, httpx, and two
dependency-free modules of our own.

The split is also where the trust boundary falls. Secrets are resolved *here*,
in the backend, and only the resolved values for the one server being called
cross to the proxy -- which is why that container needs neither the Fernet key
nor Vault credentials.
"""

import re

from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from infrastructure.secret_resolver import SecretResolver
from models.mcp_server import ENV_ARG_PLACEHOLDER_PATTERN, MCPServer, McpTransport
from repositories.exceptions import McpConnectionError


def _expand_env_args(
    args: list[str], env: dict[str, str], server_name: str
) -> list[str]:
    """Substitute ``${env:NAME}`` in each ``args`` entry with its ``env`` value.

    Args:
        args: The raw ``argv`` entries, possibly containing placeholders.
        env: The server's *resolved* env mapping (secrets already expanded).
        server_name: Identifies the server in a raised error.

    Returns:
        ``args`` with every placeholder replaced by its ``env`` value.

    Raises:
        McpConnectionError: If a placeholder names a key absent from ``env``
            — only reachable for a row written outside the API, since both
            create and update validate every reference against the server's
            own ``env`` keys.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise McpConnectionError(
                server_name, f"args reference unknown env var: {name}"
            )
        return env[name]

    return [ENV_ARG_PLACEHOLDER_PATTERN.sub(_replace, arg) for arg in args]


async def resolve_connection(
    server: MCPServer, resolver: SecretResolver
) -> McpConnection:
    """Build the connection spec for a registered server, resolving its secrets.

    Args:
        server: The registered MCP server row.
        resolver: Resolver expanding ``${secret:NAME/KEY}`` placeholders in the
            server's header (remote) or environment (stdio) values.

    Returns:
        An :data:`infrastructure.mcp_client.McpConnection` ready to hand to an
        :class:`infrastructure.mcp_executor.McpExecutor`.

    Raises:
        McpConnectionError: If the row is missing the field its transport
            requires, or a stdio row's ``args`` embed a ``${env:NAME}``
            placeholder naming a key absent from ``env`` — both only
            reachable for a row written outside the API, since create and
            update validate the per-transport shape and env references.
        repositories.exceptions.SecretResolutionError: If a referenced secret
            cannot be resolved.
    """
    if server.transport is McpTransport.stdio:
        if not server.command:
            raise McpConnectionError(server.name, "stdio server has no command")
        resolved_env = await resolver.resolve_mapping(server.env)
        return StdioConnection(
            command=server.command,
            args=_expand_env_args(list(server.args), resolved_env, server.name),
            env=resolved_env,
            raw_args=list(server.args),
        )
    if not server.url:
        raise McpConnectionError(server.name, "streamable_http server has no url")
    return HttpConnection(
        url=server.url,
        headers=await resolver.resolve_mapping(server.headers),
    )
