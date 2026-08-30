"""Admin-only read API for the impersonation audit trail.

Exposes List (paginated) and Get over ``ImpersonationEvent`` rows. There is
deliberately no Create, Update, or Delete route: a session is opened and closed
by :class:`services.impersonation.ImpersonationService` as an admin starts and
stops acting as someone, and a record an admin could edit or remove would not be
evidence of anything (see :mod:`models.impersonation_event`).

Every route is gated behind ``admin`` (``super_admin`` passes through
:func:`models.user.has_role`'s bypass).

Scoping differs from every other resource here, because the table has no
``tenant_id`` of its own: rows are narrowed by the *impersonated user's* tenant.
An admin therefore sees the sessions that touched their own tenant's users,
including ones a platform-scoped ``super_admin`` opened -- see
:mod:`repositories.impersonation_event`. A platform-scoped caller still selects a
tenant via the ``X-Tenant-Id`` request header, and may send
:data:`dependencies.auth.ALL_TENANTS_SENTINEL` to browse every tenant at once.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    FilterDep,
    ImpersonationEventServiceDep,
    PaginationDep,
    SortDep,
    require_roles,
)
from models.impersonation_event import ImpersonationEventRead
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/impersonation-events", tags=["impersonation-events"])

#: Route dependency gating every route behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get(
    "",
    response_model=ApiResponse[list[ImpersonationEventRead]],
    dependencies=_requires_admin,
)
async def list_impersonation_events(
    service: ImpersonationEventServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ImpersonationEventRead]]:
    """Return a page of recorded impersonation sessions.

    A row with no ``endedAt`` is a session still in progress. Defaults to
    ``startedAt`` descending -- this table has no ``createdAt`` column. A
    platform-scoped ``super_admin`` may select ``X-Tenant-Id: __all__`` to list
    across every tenant at once.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get(
    "/{event_id}",
    response_model=ApiResponse[ImpersonationEventRead],
    dependencies=_requires_admin,
)
async def get_impersonation_event(
    event_id: str,
    service: ImpersonationEventServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[ImpersonationEventRead]:
    """Return a single recorded impersonation session.

    Raises HTTP 404 (not 403) for a session whose impersonated user belongs to
    another tenant, so its existence is never confirmed to the caller -- unless
    the caller has selected ``X-Tenant-Id: __all__``, in which case any tenant's
    session resolves.
    """
    event = await service.get(event_id)
    return ApiResponse(meta=meta, data=event)
