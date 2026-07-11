"""CRUD endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowSession.
Listing the tasks of a particular session is exposed on the WorkflowSession
router as ``GET /workflow-sessions/{session_id}/workflow-tasks``; this router
focuses on the create-and-act-on-a-single-task operations. Every operation is
restricted to the parent session's owner, its designated approvers, and super
admins (enforced by :class:`~services.workflow_task.WorkflowTaskService`).
"""

from fastapi import APIRouter

from dependencies import ApiMetaDep, CurrentUserDep, WorkflowTaskServiceDep
from models.response import ApiResponse
from models.workflow_task import (
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)

router = APIRouter(prefix="/workflow-tasks", tags=["workflow-tasks"])


@router.post("", response_model=ApiResponse[WorkflowTaskRead], status_code=201)
async def create_workflow_task(
    body: WorkflowTaskCreate,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskRead]:
    """Create a new WorkflowTask belonging to the session named in ``body``."""
    task = await service.create(body, caller=caller)
    return ApiResponse(meta=meta, data=task)


@router.get("/{task_id}", response_model=ApiResponse[WorkflowTaskRead])
async def get_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskRead]:
    """Return the WorkflowTask with the given ID, or HTTP 404 if missing."""
    task = await service.get(task_id, caller=caller)
    return ApiResponse(meta=meta, data=task)


@router.patch("/{task_id}", response_model=ApiResponse[WorkflowTaskRead])
async def update_workflow_task(
    task_id: str,
    body: WorkflowTaskUpdate,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskRead]:
    """Apply a partial update to the WorkflowTask with the given ID."""
    task = await service.update(task_id, body, caller=caller)
    return ApiResponse(meta=meta, data=task)


@router.delete("/{task_id}", response_model=ApiResponse[None])
async def delete_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete the WorkflowTask with the given ID, raising 404 if it does not exist."""
    await service.delete(task_id, caller=caller)
    return ApiResponse(meta=meta, data=None)
