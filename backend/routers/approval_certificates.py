"""Admin-only read API for the tenant-wide approval-certificate audit trail.

Exposes List (paginated) and Get over ``ApprovalCertificate`` rows, scoped to the
acting tenant and serialized as
:class:`~models.approval_certificate.ApprovalCertificateRead` -- so the leaf's
private key and the PEM itself never leave the server, and the granted tools are
parsed back out of the signed certificate rather than read from a column.

There is deliberately no Create, Update, or Delete route. A certificate is minted
by :class:`services.approval_certificate.ApprovalCertificateService` when an
approval is granted and revoked by the same service when the task it authorized
finishes; a certificate's contents are signed, so the only thing that can change
after issuance is whether it still counts (see
:mod:`models.approval_certificate`).

Every route is gated behind ``admin`` (``super_admin`` passes through
:func:`models.user.has_role`'s bypass). ``GET /approvals/{id}/certificate`` stays
open to any authenticated caller because it discloses nothing the approval record
does not already; this surface instead spans every approval in the tenant.

Like every other tenant-scoped resource, a platform-scoped ``super_admin`` (one
who carries no ``tenant_id`` of their own) must select a tenant via the
``X-Tenant-Id`` request header before these routes resolve, and may send
:data:`dependencies.auth.ALL_TENANTS_SENTINEL` to browse across every tenant at
once; see ``CurrentTenantScopeDep`` in ``dependencies/auth.py``.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    ApprovalCertificateReadServiceDep,
    FilterDep,
    PaginationDep,
    SortDep,
    require_roles,
)
from models.approval_certificate import ApprovalCertificateRead
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/approval-certificates", tags=["approval-certificates"])

#: Route dependency gating every route behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get(
    "",
    response_model=ApiResponse[list[ApprovalCertificateRead]],
    dependencies=_requires_admin,
)
async def list_approval_certificates(
    service: ApprovalCertificateReadServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ApprovalCertificateRead]]:
    """Return a page of the acting tenant's approval certificates.

    Each row reports what one granted approval authorized: which tools, until
    when, and whether the certificate has since been revoked.

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
    "/{certificate_id}",
    response_model=ApiResponse[ApprovalCertificateRead],
    dependencies=_requires_admin,
)
async def get_approval_certificate_by_id(
    certificate_id: str,
    service: ApprovalCertificateReadServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[ApprovalCertificateRead]:
    """Return a single approval certificate by its own ID.

    Raises HTTP 404 (not 403) for a certificate belonging to another tenant, so
    its existence is never confirmed to the caller -- unless the caller has
    selected ``X-Tenant-Id: __all__``, in which case any tenant's row resolves.
    """
    certificate = await service.read(certificate_id)
    return ApiResponse(meta=meta, data=certificate)
