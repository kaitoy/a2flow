"""CRUD endpoints for MCPToolMock resources.

A mock stands in for one tool during a draft workflow run. Writes are gated
behind ``developer``, matching MCP server registration: choosing what a tool
returns instead of calling it is a build-time decision about how a workflow is
tested, not something a requester should be able to change.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    MCPToolMockReadServiceDep,
    MCPToolMockServiceDep,
    PaginationDep,
    SortDep,
    TagFilterDep,
    require_roles,
)
from models.mcp_tool_mock import (
    McpToolMockCreate,
    McpToolMockRead,
    McpToolMockUpdate,
)
from models.response import ApiResponse
from models.tag import TagIdsUpdate
from models.user import Role

router = APIRouter(prefix="/mcp-tool-mocks", tags=["mcp-tool-mocks"])

#: Route dependency gating tool-mock writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[McpToolMockRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_mcp_tool_mock(
    body: McpToolMockCreate,
    service: MCPToolMockServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpToolMockRead]:
    mock = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(mock))


@router.get("", response_model=ApiResponse[list[McpToolMockRead]])
async def list_mcp_tool_mocks(
    service: MCPToolMockReadServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    tags: TagFilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[McpToolMockRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        tag_ids=tags.tag_ids,
    )
    return ApiResponse(meta=meta, data=await service.to_read_many(items))


@router.get("/{mock_id}", response_model=ApiResponse[McpToolMockRead])
async def get_mcp_tool_mock(
    mock_id: str,
    service: MCPToolMockReadServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpToolMockRead]:
    mock = await service.get(mock_id)
    return ApiResponse(meta=meta, data=await service.to_read(mock))


@router.patch(
    "/{mock_id}",
    response_model=ApiResponse[McpToolMockRead],
    dependencies=_requires_developer,
)
async def update_mcp_tool_mock(
    mock_id: str,
    body: McpToolMockUpdate,
    service: MCPToolMockServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpToolMockRead]:
    mock = await service.update(mock_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(mock))


@router.delete(
    "/{mock_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_mcp_tool_mock(
    mock_id: str,
    service: MCPToolMockServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(mock_id)
    return ApiResponse(meta=meta, data=None)


@router.put(
    "/{mock_id}/tags",
    response_model=ApiResponse[McpToolMockRead],
    dependencies=_requires_developer,
)
async def set_mcp_tool_mock_tags(
    mock_id: str,
    body: TagIdsUpdate,
    service: MCPToolMockServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpToolMockRead]:
    mock = await service.set_tags(mock_id, body.tag_ids)
    return ApiResponse(meta=meta, data=await service.to_read(mock))
