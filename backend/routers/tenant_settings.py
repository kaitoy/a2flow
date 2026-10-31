"""Endpoints for the settings a tenant's own ``admin`` manages.

Unlike :mod:`routers.tenant` (``super_admin`` only, addressed by tenant id),
these routes act on the caller's tenant (``CurrentTenantIdDep``: their own, or
the one a ``super_admin`` selected with ``X-Tenant-Id``) and expose only the
fields an ``admin`` may change -- today, sign-in throttling.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.service import TenantServiceDep
from models.response import ApiResponse
from models.tenant import Tenant, TenantSettings, TenantSettingsUpdate, TenantUpdate
from models.user import Role

router = APIRouter(prefix="/tenant-settings", tags=["tenant-settings"])

#: Route dependency gating both routes behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


def _to_read(tenant: Tenant) -> TenantSettings:
    """Project a tenant into its admin-managed settings."""
    return TenantSettings(
        login_max_failures=tenant.login_max_failures,
        login_lockout_minutes=tenant.login_lockout_minutes,
    )


@router.get(
    "", response_model=ApiResponse[TenantSettings], dependencies=_requires_admin
)
async def get_tenant_settings(
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[TenantSettings]:
    """Return the caller's tenant's admin-managed settings."""
    return ApiResponse(meta=meta, data=_to_read(await service.get(tenant_id)))


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
    tenant = await service.update(
        tenant_id,
        TenantUpdate(**body.model_dump(exclude_unset=True)),
        user_id=user_id,
    )
    return ApiResponse(meta=meta, data=_to_read(tenant))
