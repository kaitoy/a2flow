"""Search endpoint for discovering MCP servers via the official registry.

This router only *reads* the official MCP registry. Registering a discovered
server reuses the ordinary ``POST /mcp-servers`` create flow from a pre-filled
admin form, so no write endpoint lives here.
"""

from fastapi import APIRouter

from dependencies import ApiMetaDep, MCPRegistryServiceDep
from models.mcp_registry import McpRegistrySearchResult
from models.response import ApiResponse

router = APIRouter(prefix="/mcp-registry", tags=["mcp-registry"])


@router.get("", response_model=ApiResponse[McpRegistrySearchResult])
async def search_mcp_registry(
    service: MCPRegistryServiceDep,
    meta: ApiMetaDep,
    search: str | None = None,
    cursor: str | None = None,
) -> ApiResponse[McpRegistrySearchResult]:
    """Search the official MCP registry for registrable servers.

    Args:
        service: Injected registry discovery service.
        meta: Injected response metadata.
        search: Optional substring matched against server names.
        cursor: Optional pagination cursor from a previous result.

    Returns:
        An envelope wrapping the page of streamable-HTTP servers and the cursor
        for the next page.
    """
    result = await service.search(search=search, cursor=cursor)
    return ApiResponse(meta=meta, data=result)
