"""Endpoints for listing, retrieving, and resolving Approval requests.

Approvals are created by the workflow agent (via the ``request_approval`` tool)
and resolved here by the approver: ``PATCH /approvals/{id}`` moves a request to
``approved`` or ``rejected``. The approver's identity (``CurrentUserIdDep``) is
recorded in the approval's audit fields. List and get are unscoped so the admin
UI can browse every approval, mirroring the workflow-sessions router.
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    ApprovalServiceDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
)
from models.approval import Approval, ApprovalUpdate
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
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Approval]:
    """Resolve an approval, recording the requesting user as the approver.

    Raises HTTP 404 if the approval does not exist.
    """
    approval = await service.resolve(approval_id, data, user_id=user_id)
    return ApiResponse(meta=meta, data=approval)
