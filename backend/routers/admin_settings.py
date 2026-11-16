"""Endpoints for the settings a tenant's own ``admin`` manages.

Unlike :mod:`routers.tenant` (``super_admin`` only, addressed by tenant id),
these routes act on the caller's tenant (``CurrentTenantIdDep``: their own, or
the one a ``super_admin`` selected with ``X-Tenant-Id``) and expose only the
fields an ``admin`` may change: sign-in throttling, the tenant's own Vault
connection (without one, the tenant reads the global Vault) and its OIDC single
sign-on, whose callback URLs derive from the deployment's ``APP_BASE_URL`` and
the tenant's own subdomain of it.
"""

from fastapi import APIRouter, Depends

from config import get_settings
from dependencies.auth import CurrentTenantIdDep, CurrentUserIdDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep
from dependencies.service import TenantServiceDep
from models.response import ApiResponse
from models.tenant import (
    AdminSettings,
    AdminSettingsUpdate,
    Tenant,
    oidc_redirect_uri,
)
from models.user import Role

router = APIRouter(prefix="/admin-settings", tags=["admin-settings"])

#: Route dependency gating both routes behind ``admin`` (``super_admin`` passes).
_requires_admin = [Depends(require_roles(Role.admin))]


def _view(tenant: Tenant) -> AdminSettings:
    """Project ``tenant`` with its OIDC callback URLs on both of its addresses.

    Args:
        tenant: The tenant whose settings are shown.

    Returns:
        The settings; a callback URL is ``None`` when its address does not exist.
    """
    settings = get_settings()
    return AdminSettings.from_tenant(
        tenant,
        oidc_redirect_uri=oidc_redirect_uri(settings.app_base_url),
        oidc_subdomain_redirect_uri=oidc_redirect_uri(
            settings.tenant_origin(tenant.name)
        ),
    )


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
        data=_view(tenant),
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
        data=_view(tenant),
    )
