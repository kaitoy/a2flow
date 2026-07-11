"""CRUD endpoints for MCPServer resources plus remote tool discovery."""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    MCPServerServiceDep,
    PaginationDep,
    SortDep,
    require_roles,
)
from models.mcp_server import MCPServer, MCPServerCreate, MCPServerUpdate, McpToolInfo
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

#: Route dependency gating MCP server writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[MCPServer],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_mcp_server(
    body: MCPServerCreate,
    service: MCPServerServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[MCPServer]:
    server = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=server)


@router.get("", response_model=ApiResponse[list[MCPServer]])
async def list_mcp_servers(
    service: MCPServerServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[MCPServer]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{server_id}", response_model=ApiResponse[MCPServer])
async def get_mcp_server(
    server_id: str,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[MCPServer]:
    server = await service.get(server_id)
    return ApiResponse(meta=meta, data=server)


@router.get("/{server_id}/tools", response_model=ApiResponse[list[McpToolInfo]])
async def list_mcp_server_tools(
    server_id: str,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[McpToolInfo]]:
    tools = await service.list_tools(server_id)
    return ApiResponse(meta=meta, data=tools)


@router.patch(
    "/{server_id}",
    response_model=ApiResponse[MCPServer],
    dependencies=_requires_developer,
)
async def update_mcp_server(
    server_id: str,
    body: MCPServerUpdate,
    service: MCPServerServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[MCPServer]:
    server = await service.update(server_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=server)


@router.delete(
    "/{server_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_mcp_server(
    server_id: str,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(server_id)
    return ApiResponse(meta=meta, data=None)
