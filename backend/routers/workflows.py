"""CRUD endpoints for Workflow resources and the workflow execution action."""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    PaginationDep,
    WorkflowServiceDep,
)
from models.response import ApiResponse
from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from models.workflow_session import WorkflowSession

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=ApiResponse[Workflow], status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.get("", response_model=ApiResponse[list[Workflow]])
async def list_workflows(
    service: WorkflowServiceDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Workflow]]:
    items = await service.list(limit=pagination.limit, offset=pagination.offset)
    return ApiResponse(meta=meta, data=items)


@router.get("/{workflow_id}", response_model=ApiResponse[Workflow])
async def get_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.get(workflow_id)
    return ApiResponse(meta=meta, data=workflow)


@router.patch("/{workflow_id}", response_model=ApiResponse[Workflow])
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.update(workflow_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.delete("/{workflow_id}", response_model=ApiResponse[None])
async def delete_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(workflow_id)
    return ApiResponse(meta=meta, data=None)


@router.post(
    "/{workflow_id}/execute",
    response_model=ApiResponse[WorkflowSession],
    status_code=201,
)
async def execute_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowSession]:
    """Create a WorkflowSession; the ADK session is created lazily on first agent call."""
    ws = await service.execute(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=ws)
