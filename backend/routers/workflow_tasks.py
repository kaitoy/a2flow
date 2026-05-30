"""CRUD endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowSession.
Listing the tasks of a particular session is exposed on the WorkflowSession
router as ``GET /workflow-sessions/{session_id}/workflow-tasks``; this router
focuses on the create-and-act-on-a-single-task operations.
"""

from fastapi import APIRouter

from dependencies import ApiMetaDep, CurrentUserIdDep, WorkflowTaskServiceDep
from models.response import ApiResponse
from models.workflow_task import WorkflowTask, WorkflowTaskCreate, WorkflowTaskUpdate

router = APIRouter(prefix="/workflow-tasks", tags=["workflow-tasks"])


@router.post("", response_model=ApiResponse[WorkflowTask], status_code=201)
async def create_workflow_task(
    body: WorkflowTaskCreate,
    service: WorkflowTaskServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTask]:
    """Create a new WorkflowTask belonging to the session named in ``body``."""
    task = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=task)


@router.get("/{task_id}", response_model=ApiResponse[WorkflowTask])
async def get_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTask]:
    """Return the WorkflowTask with the given ID, or HTTP 404 if missing."""
    task = await service.get(task_id)
    return ApiResponse(meta=meta, data=task)


@router.patch("/{task_id}", response_model=ApiResponse[WorkflowTask])
async def update_workflow_task(
    task_id: str,
    body: WorkflowTaskUpdate,
    service: WorkflowTaskServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTask]:
    """Apply a partial update to the WorkflowTask with the given ID."""
    task = await service.update(task_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=task)


@router.delete("/{task_id}", response_model=ApiResponse[None])
async def delete_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete the WorkflowTask with the given ID, raising 404 if it does not exist."""
    await service.delete(task_id)
    return ApiResponse(meta=meta, data=None)
