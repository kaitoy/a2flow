"""Endpoints for the settings a tenant's own ``admin`` manages.

Unlike :mod:`routers.tenant` (``super_admin`` only, addressed by tenant id),
these routes act on the caller's tenant (``CurrentTenantIdDep``: their own, or
the one a ``super_admin`` selected with ``X-Tenant-Id``) and expose only the
fields an ``admin`` may change: sign-in throttling, the tenant's own Vault
connection (without one, the tenant reads the global Vault) and its OIDC single
sign-on, whose callback URL derives from the deployment's ``APP_BASE_URL``.
"""

from fastapi import APIRouter, Depends

from config import get_settings
from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.service import TenantServiceDep
from models.response import ApiResponse
from models.tenant import AdminSettings, AdminSettingsUpdate, oidc_redirect_uri
from models.user import Role

router = APIRouter(prefix="/admin-settings", tags=["admin-settings"])

#: Route dependency gating both routes behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


def _redirect_uri() -> str | None:
    """Return the OIDC callback URL under the deployment's ``APP_BASE_URL``.

    Returns:
        The callback URL, or ``None`` when no base URL is configured.
    """
    return oidc_redirect_uri(get_settings().app_base_url)


@router.get("", response_model=ApiResponse[AdminSettings], dependencies=_requires_admin)
async def get_admin_settings(
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[AdminSettings]:
    """Return the caller's tenant's admin-managed settings."""
    tenant = await service.get(tenant_id)
    return ApiResponse(
        meta=meta,
        data=AdminSettings.from_tenant(tenant, oidc_redirect_uri=_redirect_uri()),
    )


@router.patch(
    "", response_model=ApiResponse[AdminSettings], dependencies=_requires_admin
)
async def update_admin_settings(
    body: AdminSettingsUpdate,
    tenant_id: CurrentTenantIdDep,
    service: TenantServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AdminSettings]:
    """Apply a partial update to the caller's tenant's admin-managed settings."""
    tenant = await service.update(tenant_id, body, user_id=user_id)
    return ApiResponse(
        meta=meta,
        data=AdminSettings.from_tenant(tenant, oidc_redirect_uri=_redirect_uri()),
    )
