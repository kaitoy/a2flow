"""Admin-only read API for the tenant-wide MCP tool-invocation audit trail.

Exposes List (paginated) and Get over ``MCPToolInvocation`` rows, scoped to the
acting tenant. There is deliberately no Create, Update, or Delete route: rows are
written only by :class:`infrastructure.mcp_audit.SqlMcpAuditSink` and are never
altered afterwards -- an audit record that a route could edit would not be
evidence of anything (see :mod:`models.mcp_tool_invocation`).

Every route is gated behind ``admin`` (``super_admin`` passes through
:func:`models.user.has_role`'s bypass). Unlike
``GET /workflow-executions/{id}/tool-invocations``, which narrows to one run and
admits that run's participants, this surface spans every run in the tenant, so a
participant-level grant would leak the calls other people's runs made.

Like every other tenant-scoped resource, a platform-scoped ``super_admin`` (one
who carries no ``tenant_id`` of their own) must select a tenant via the
``X-Tenant-Id`` request header before these routes resolve, and may send
:data:`dependencies.auth.ALL_TENANTS_SENTINEL` to browse across every tenant at
once; see ``CurrentTenantScopeDep`` in ``dependencies/auth.py``.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    FilterDep,
    McpToolInvocationServiceDep,
    PaginationDep,
    SortDep,
    require_roles,
)
from models.mcp_tool_invocation import MCPToolInvocation
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/mcp-tool-invocations", tags=["mcp-tool-invocations"])

#: Route dependency gating every route behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get(
    "",
    response_model=ApiResponse[list[MCPToolInvocation]],
    dependencies=_requires_admin,
)
async def list_mcp_tool_invocations(
    service: McpToolInvocationServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[MCPToolInvocation]]:
    """Return a page of the acting tenant's recorded MCP tool-call decisions.

    These are the calls that reached the MCP proxy: ``allowed`` ones that went
    upstream and ``denied`` ones a policy vetoed. Calls answered by a tool mock
    never reach the proxy and are therefore absent. Arguments appear only as
    ``argumentsDigest``; the raw values are never recorded.

    Defaults to ``createdAt`` descending. A platform-scoped ``super_admin`` may
    select ``X-Tenant-Id: __all__`` to list across every tenant at once.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get(
    "/{invocation_id}",
    response_model=ApiResponse[MCPToolInvocation],
    dependencies=_requires_admin,
)
async def get_mcp_tool_invocation(
    invocation_id: str,
    service: McpToolInvocationServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[MCPToolInvocation]:
    """Return a single recorded MCP tool-call decision.

    Raises HTTP 404 (not 403) for a record belonging to another tenant, so its
    existence is never confirmed to the caller -- unless the caller has selected
    ``X-Tenant-Id: __all__``, in which case any tenant's record resolves.
    """
    invocation = await service.get(invocation_id)
    return ApiResponse(meta=meta, data=invocation)
