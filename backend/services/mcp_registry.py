"""Use case service for searching the official MCP registry.

Thin wrapper over :mod:`infrastructure.mcp_registry_client`. There is no
repository because the registry is an external read-only API with no local
persistence; registration itself reuses the ordinary ``POST /mcp-servers``
create flow once the operator confirms the pre-filled form.
"""

from infrastructure import mcp_registry_client
from models.mcp_registry import McpRegistrySearchResult


class MCPRegistryService:
    """Application service for discovering MCP servers via the official registry."""

    async def search(
        self, *, search: str | None = None, cursor: str | None = None
    ) -> McpRegistrySearchResult:
        """Search the registry for registrable (streamable-HTTP) servers.

        Args:
            search: Substring matched against server names; ``None`` lists servers.
            cursor: Pagination cursor from a previous result; ``None`` for page one.

        Returns:
            A page of registrable servers plus the cursor for the next page.

        Raises:
            RegistryUnavailableError: If the registry cannot be reached.
        """
        return await mcp_registry_client.search_servers(search, cursor)
