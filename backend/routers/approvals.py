"""Endpoints for listing, retrieving, and resolving Approval requests.

Approvals are created by the workflow agent (via the ``request_approval`` tool)
and resolved here by the approver: ``PATCH /approvals/{id}`` moves a request to
``approved``, ``rejected``, or ``returned``. Only the designated approver may
resolve a request -- with no exception, not even for a super admin or an admin;
the resolver's identity is recorded in the approval's audit fields. List is
scoped like ``GET /workflow-executions``: a super admin or admin sees every
approval in the tenant, everyone else sees only approvals addressed to them or
belonging to a WorkflowExecution they initiated. Get remains unscoped -- any
authenticated user may fetch any single approval by id.

``GET /approvals/by-approver`` and ``GET /approvals/by-workflow`` aggregate the
same records into approval-backlog breakdowns for operational dashboards. Both
are declared before ``/{approval_id}`` so their literal path segment is matched
first.

``GET /approvals/{id}/certificate`` returns the X.509 certificate issued when
the approval was granted -- the thing that actually lets the approved task call
its bound MCP tools (see :mod:`models.approval_certificate`).
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    ApprovalCertificateServiceDep,
    ApprovalServiceDep,
    BacklogThresholdDep,
    CurrentUserDep,
    EffectiveRolesDep,
    FilterDep,
    MetricsServiceDep,
    PaginationDep,
    SortDep,
)
from models.approval import Approval, ApprovalUpdate
from models.approval_certificate import ApprovalCertificateRead
from models.metrics import ApprovalBacklogEntry
from models.response import ApiResponse

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=ApiResponse[list[Approval]])
async def list_approvals(
    service: ApprovalServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Approval]]:
    """Return Approval records, defaulting to ``created_at`` descending.

    A super admin or admin sees every approval in the tenant; anyone else
    sees only approvals addressed to them or belonging to a
    WorkflowExecution they initiated.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        caller=caller,
        caller_roles=caller_roles,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/by-approver", response_model=ApiResponse[list[ApprovalBacklogEntry]])
async def approval_backlog_by_approver(
    service: MetricsServiceDep,
    threshold: BacklogThresholdDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ApprovalBacklogEntry]]:
    """Return the pending-approval backlog grouped by approval destination.

    Entries come back longest-single-wait first, so ``?limit=5`` is the worst
    five destinations. ``groupKind`` says what ``groupId`` is: ``"user"`` for an
    approval addressed to one person — resolve the id to a name through
    ``POST /users/resolve-names`` — or ``"group"`` for one addressed to a user
    group, in which case ``groupLabel`` already carries the group's name. Both
    are ``null`` for approvals with no designated destination.
    """
    entries = await service.approval_backlog_by_approver(
        threshold_hours=threshold.threshold_hours, limit=pagination.limit
    )
    return ApiResponse(meta=meta, data=entries)


@router.get("/by-workflow", response_model=ApiResponse[list[ApprovalBacklogEntry]])
async def approval_backlog_by_workflow(
    service: MetricsServiceDep,
    threshold: BacklogThresholdDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ApprovalBacklogEntry]]:
    """Return the pending-approval backlog grouped by workflow.

    The other axis of the same view: which workflows accumulate approval waits,
    rather than which people do. ``groupId`` is the workflow id and
    ``groupLabel`` its name.
    """
    entries = await service.approval_backlog_by_workflow(
        threshold_hours=threshold.threshold_hours, limit=pagination.limit
    )
    return ApiResponse(meta=meta, data=entries)


@router.get("/{approval_id}", response_model=ApiResponse[Approval])
async def get_approval(
    approval_id: str,
    service: ApprovalServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Approval]:
    """Return the Approval record for the given ID."""
    approval = await service.get(approval_id)
    return ApiResponse(meta=meta, data=approval)


@router.get(
    "/{approval_id}/certificate", response_model=ApiResponse[ApprovalCertificateRead]
)
async def get_approval_certificate(
    approval_id: str,
    service: ApprovalCertificateServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[ApprovalCertificateRead]:
    """Return the certificate issued when this approval was granted.

    Reports what the approval actually authorized: which tools, until when, and
    whether the certificate has since been revoked. The granted tools are parsed
    back out of the signed certificate rather than read from a column, so this
    can never disagree with what the certificate says. The private key is never
    part of the response.

    Scoped like ``GET /approvals/{id}``: any authenticated user may fetch it,
    since it discloses nothing the approval record does not already.

    Raises:
        NotFoundError: If the approval has no certificate -- because it was
            never granted, or because it named no task and so granted no tool
            authority.
    """
    certificate = await service.read_for_approval(approval_id)
    return ApiResponse(meta=meta, data=certificate)


@router.patch("/{approval_id}", response_model=ApiResponse[Approval])
async def resolve_approval(
    approval_id: str,
    data: ApprovalUpdate,
    service: ApprovalServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[Approval]:
    """Resolve an approval, recording the requesting user as the approver.

    Accepts ``approved``, ``rejected``, or ``returned`` (sent back for rework).
    Only the designated approver may resolve -- with no exception, not even
    for a super admin or an admin; anyone else receives HTTP 403
    (``FORBIDDEN``). Raises HTTP 404 if the approval does not exist. The
    transition out of ``pending`` stamps the server-managed ``decidedAt``.
    """
    approval = await service.resolve(approval_id, data, acting_user=acting_user)
    return ApiResponse(meta=meta, data=approval)
