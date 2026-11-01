"""Endpoints for the settings a tenant's own ``admin`` manages.

Unlike :mod:`routers.tenant` (``super_admin`` only, addressed by tenant id),
these routes act on the caller's tenant (``CurrentTenantIdDep``: their own, or
the one a ``super_admin`` selected with ``X-Tenant-Id``) and expose only the
fields an ``admin`` may change: sign-in throttling and the tenant's own
Vault connection (without one, the tenant reads the global Vault).
"""

from fastapi import APIRouter, Depends

from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.service import TenantServiceDep
from models.response import ApiResponse
from models.tenant import TenantSettings, TenantSettingsUpdate
from models.user import Role

router = APIRouter(prefix="/tenant-settings", tags=["tenant-settings"])

#: Route dependency gating both routes behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get(
    "", response_model=ApiResponse[TenantSettings], dependencies=_requires_admin
)
async def get_tenant_settings(
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[TenantSettings]:
    """Return the caller's tenant's admin-managed settings."""
    return ApiResponse(
        meta=meta, data=TenantSettings.from_tenant(await service.get(tenant_id))
    )


@router.patch(
    "", response_model=ApiResponse[TenantSettings], dependencies=_requires_admin
)
async def update_tenant_settings(
    body: TenantSettingsUpdate,
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[TenantSettings]:
    """Apply a partial update to the caller's tenant's admin-managed settings."""
    tenant = await service.update(tenant_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=TenantSettings.from_tenant(tenant))
