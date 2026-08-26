"""Super-admin-only read/delete API for the outgoing-email queue.

Exposes List (paginated), Get, and Delete over ``OutboundEmail`` rows, scoped
to the caller's own tenant. There is deliberately no Create or Update route:
rows are written only by :class:`services.notification_dispatch.NotificationDispatcher`
and mutated only by the queue worker's named lifecycle steps -- see
:mod:`models.outbound_email`.

Every route, not just writes, is gated behind ``super_admin`` -- unlike most
resource routers here, which leave reads open to any authenticated caller,
this surface exposes every queued message's recipient and body across the
tenant, matching the same shape as :mod:`routers.system_settings`.

Like every other tenant-scoped resource, a platform-scoped ``super_admin``
(one who carries no ``tenant_id`` of their own) must select a tenant via the
``X-Tenant-Id`` request header before these routes resolve. List and Get,
unlike Delete, additionally accept :data:`dependencies.auth.ALL_TENANTS_SENTINEL`
in that header to browse the queue across every tenant at once, the same
"all tenants" read mode every other resource router supports; see
``CurrentTenantScopeDep`` in ``dependencies/auth.py``.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    FilterDep,
    OutboundEmailReadServiceDep,
    OutboundEmailServiceDep,
    PaginationDep,
    SortDep,
    require_roles,
)
from models.outbound_email import OutboundEmailRead
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/outbound-emails", tags=["outbound-emails"])

#: Route dependency gating every outbound-email route behind the ``super_admin`` role.
_requires_super_admin = [Depends(require_roles(Role.super_admin))]


@router.get(
    "",
    response_model=ApiResponse[list[OutboundEmailRead]],
    dependencies=_requires_super_admin,
)
async def list_outbound_emails(
    service: OutboundEmailReadServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[OutboundEmailRead]]:
    """Return a page of the acting tenant's outbound-email queue rows.

    Defaults to ``createdAt`` descending. A platform-scoped ``super_admin``
    may select ``X-Tenant-Id: __all__`` to list across every tenant at once.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get(
    "/{email_id}",
    response_model=ApiResponse[OutboundEmailRead],
    dependencies=_requires_super_admin,
)
async def get_outbound_email(
    email_id: str,
    service: OutboundEmailReadServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[OutboundEmailRead]:
    """Return a single outbound-email queue row.

    Raises HTTP 404 (not 403) for a row belonging to another tenant, so its
    existence is never confirmed to the caller -- unless the caller has
    selected ``X-Tenant-Id: __all__``, in which case any tenant's row resolves.
    """
    email = await service.get(email_id)
    return ApiResponse(meta=meta, data=email)


@router.delete(
    "/{email_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_super_admin,
)
async def delete_outbound_email(
    email_id: str,
    service: OutboundEmailServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete an outbound-email queue row.

    Only permitted once the row has reached a terminal status (``sent`` or
    ``failed``); a ``pending``/``sending`` row may be actively claimed by the
    queue worker, and deleting it instead raises HTTP 409
    (``OUTBOUND_EMAIL_NOT_DELETABLE``).
    """
    await service.delete(email_id)
    return ApiResponse(meta=meta, data=None)
