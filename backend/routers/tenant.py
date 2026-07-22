"""CRUD endpoints for Tenant resources.

Tenants are the platform-wide organizational boundary (see
:mod:`models.tenant`), so every write is gated behind the ``super_admin``
role — unlike most resources, there is no self-service or ``admin``-level
carve-out.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    TenantServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.tenant import Tenant, TenantCreate, TenantUpdate
from models.user import Role

router = APIRouter(prefix="/tenants", tags=["tenants"])

#: Route dependency gating every tenant write behind the ``super_admin`` role.
_requires_super_admin = [Depends(require_roles(Role.super_admin))]


@router.post(
    "",
    response_model=ApiResponse[Tenant],
    status_code=201,
    dependencies=_requires_super_admin,
)
async def create_tenant(
    body: TenantCreate,
    service: TenantServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tenant]:
    """Create a new tenant."""
    tenant = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=tenant)


@router.get("", response_model=ApiResponse[list[Tenant]])
async def list_tenants(
    service: TenantServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Tenant]]:
    """Return a page of tenants."""
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{tenant_id}", response_model=ApiResponse[Tenant])
async def get_tenant(
    tenant_id: str,
    service: TenantServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tenant]:
    """Return a single tenant."""
    tenant = await service.get(tenant_id)
    return ApiResponse(meta=meta, data=tenant)


@router.patch(
    "/{tenant_id}",
    response_model=ApiResponse[Tenant],
    dependencies=_requires_super_admin,
)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    service: TenantServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Tenant]:
    """Apply a partial update to a tenant."""
    tenant = await service.update(tenant_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=tenant)


@router.delete(
    "/{tenant_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_super_admin,
)
async def delete_tenant(
    tenant_id: str,
    service: TenantServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a tenant.

    Fails with ``CONFLICT_REFERENCED`` while any user remains assigned to it.
    """
    await service.delete(tenant_id)
    return ApiResponse(meta=meta, data=None)
