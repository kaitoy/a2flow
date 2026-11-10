"""Endpoints for the settings a tenant's own ``admin`` manages.

Unlike :mod:`routers.tenant` (``super_admin`` only, addressed by tenant id),
these routes act on the caller's tenant (``CurrentTenantIdDep``: their own, or
the one a ``super_admin`` selected with ``X-Tenant-Id``) and expose only the
fields an ``admin`` may change: sign-in throttling, the tenant's own Vault
connection (without one, the tenant reads the global Vault) and its OIDC single
sign-on, whose callback URL derives from the platform's ``app_base_url``.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.repository import SystemSettingsRepositoryDep
from dependencies.service import TenantServiceDep
from models.response import ApiResponse
from models.tenant import TenantSettings, TenantSettingsUpdate, oidc_redirect_uri
from models.user import Role

router = APIRouter(prefix="/tenant-settings", tags=["tenant-settings"])

#: Route dependency gating both routes behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


async def _redirect_uri(system_settings: SystemSettingsRepositoryDep) -> str | None:
    """Return the OIDC callback URL under the platform's ``app_base_url``.

    Args:
        system_settings: Repository of the singleton system-settings row.

    Returns:
        The callback URL, or ``None`` when no base URL is configured.
    """
    row = await system_settings.get()
    return oidc_redirect_uri(row.app_base_url if row else None)


@router.get(
    "", response_model=ApiResponse[TenantSettings], dependencies=_requires_admin
)
async def get_tenant_settings(
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    system_settings: SystemSettingsRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[TenantSettings]:
    """Return the caller's tenant's admin-managed settings."""
    tenant = await service.get(tenant_id)
    return ApiResponse(
        meta=meta,
        data=TenantSettings.from_tenant(
            tenant, oidc_redirect_uri=await _redirect_uri(system_settings)
        ),
    )


@router.patch(
    "", response_model=ApiResponse[TenantSettings], dependencies=_requires_admin
)
async def update_tenant_settings(
    body: TenantSettingsUpdate,
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    system_settings: SystemSettingsRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[TenantSettings]:
    """Apply a partial update to the caller's tenant's admin-managed settings."""
    tenant = await service.update(tenant_id, body, user_id=user_id)
    return ApiResponse(
        meta=meta,
        data=TenantSettings.from_tenant(
            tenant, oidc_redirect_uri=await _redirect_uri(system_settings)
        ),
    )
