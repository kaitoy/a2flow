"""CRUD endpoints for MCPServer resources plus remote tool discovery."""

from fastapi import APIRouter, Depends

from dependencies.auth import CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import (
    ApiMetaDep,
    FilterDep,
    PaginationDep,
    SortDep,
    TagFilterDep,
)
from dependencies.service import MCPServerServiceDep
from models.mcp_server import (
    MCPServerCreate,
    McpServerRead,
    MCPServerUpdate,
    McpToolInfo,
    PythonLintRequest,
    ScriptCallRequest,
    ScriptCallResult,
    ScriptDiagnostic,
    ScriptTestRequest,
    ScriptToolsResult,
    lint_python_script,
)
from models.response import ApiResponse
from models.tag import TagIdsUpdate
from models.user import Role

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])

#: Route dependency gating MCP server writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[McpServerRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_mcp_server(
    body: MCPServerCreate,
    service: MCPServerServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpServerRead]:
    server = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(server))


@router.post(
    "/python-lint",
    response_model=ApiResponse[list[ScriptDiagnostic]],
    dependencies=_requires_developer,
)
async def lint_python(
    body: PythonLintRequest,
    meta: ApiMetaDep,
) -> ApiResponse[list[ScriptDiagnostic]]:
    """Check a Python script server's source for the editor to underline."""
    return ApiResponse(meta=meta, data=lint_python_script(body.source, body.packages))


@router.post(
    "/script-tools",
    response_model=ApiResponse[ScriptToolsResult],
    dependencies=_requires_developer,
)
async def list_script_tools(
    body: ScriptTestRequest,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[ScriptToolsResult]:
    """Load an unsaved script and list its tools, or report why it cannot load."""
    return ApiResponse(meta=meta, data=await service.test_script_tools(body))


@router.post(
    "/script-call",
    response_model=ApiResponse[ScriptCallResult],
    dependencies=_requires_developer,
)
async def call_script_tool(
    body: ScriptCallRequest,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[ScriptCallResult]:
    """Run one tool of an unsaved script and return what it produced."""
    return ApiResponse(meta=meta, data=await service.test_script_call(body))


@router.get("", response_model=ApiResponse[list[McpServerRead]])
async def list_mcp_servers(
    service: MCPServerServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    tags: TagFilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[McpServerRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        tag_ids=tags.tag_ids,
    )
    return ApiResponse(meta=meta, data=await service.to_read_many(items))


@router.get("/{server_id}", response_model=ApiResponse[McpServerRead])
async def get_mcp_server(
    server_id: str,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpServerRead]:
    server = await service.get(server_id)
    return ApiResponse(meta=meta, data=await service.to_read(server))


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
    response_model=ApiResponse[McpServerRead],
    dependencies=_requires_developer,
)
async def update_mcp_server(
    server_id: str,
    body: MCPServerUpdate,
    service: MCPServerServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpServerRead]:
    server = await service.update(server_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(server))


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


@router.put(
    "/{server_id}/tags",
    response_model=ApiResponse[McpServerRead],
    dependencies=_requires_developer,
)
async def set_mcp_server_tags(
    server_id: str,
    body: TagIdsUpdate,
    service: MCPServerServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[McpServerRead]:
    server = await service.set_tags(server_id, body.tag_ids)
    return ApiResponse(meta=meta, data=await service.to_read(server))
