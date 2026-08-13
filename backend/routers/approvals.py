"""Endpoints for listing, retrieving, and resolving Approval requests.

Approvals are created by the workflow agent (via the ``request_approval`` tool)
and resolved here by the approver: ``PATCH /approvals/{id}`` moves a request to
``approved``, ``rejected``, or ``returned``. Only the designated approver (or a
super admin) may resolve a request; the resolver's identity is recorded in the
approval's audit fields. List and get are unscoped so the admin UI can browse
every approval, mirroring the workflow-executions router.

``GET /approvals/by-approver`` and ``GET /approvals/by-workflow`` aggregate the
same records into approval-backlog breakdowns for operational dashboards. Both
are declared before ``/{approval_id}`` so their literal path segment is matched
first.
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    ApprovalServiceDep,
    BacklogThresholdDep,
    CurrentUserDep,
    FilterDep,
    MetricsServiceDep,
    PaginationDep,
    SortDep,
)
from models.approval import Approval, ApprovalUpdate
from models.metrics import ApprovalBacklogEntry
from models.response import ApiResponse

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=ApiResponse[list[Approval]])
async def list_approvals(
    service: ApprovalServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Approval]]:
    """Return Approval records, defaulting to ``created_at`` descending."""
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
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
    """Return the pending-approval backlog grouped by designated approver.

    Entries come back longest-single-wait first, so ``?limit=5`` is the worst
    five approvers. ``groupId`` is the approver's user id — resolve it to a name
    through ``POST /users/resolve-names`` — and is ``null`` for approvals with no
    designated approver.
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
    Only the designated approver or a super admin may resolve; anyone else
    receives HTTP 403 (``FORBIDDEN``). Raises HTTP 404 if the approval does
    not exist. The transition out of ``pending`` stamps the server-managed
    ``decidedAt``.
    """
    approval = await service.resolve(approval_id, data, acting_user=acting_user)
    return ApiResponse(meta=meta, data=approval)
