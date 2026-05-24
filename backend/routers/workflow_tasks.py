"""CRUD endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowSession.
Listing the tasks of a particular session is exposed on the WorkflowSession
router as ``GET /workflow-sessions/{session_id}/workflow-tasks``; this router
focuses on the create-and-act-on-a-single-task operations.
"""

from fastapi import APIRouter

from dependencies import CurrentUserIdDep, WorkflowTaskRepositoryDep
from models.workflow_task import WorkflowTask, WorkflowTaskCreate, WorkflowTaskUpdate
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/workflow-tasks", tags=["workflow-tasks"])


@router.post("", response_model=WorkflowTask, status_code=201)
async def create_workflow_task(
    body: WorkflowTaskCreate,
    repo: WorkflowTaskRepositoryDep,
    user_id: CurrentUserIdDep,
) -> WorkflowTask:
    """Create a new WorkflowTask belonging to the session named in ``body``."""
    return await repo.create(body, user_id=user_id)


@router.get("/{task_id}", response_model=WorkflowTask)
async def get_workflow_task(
    task_id: str, repo: WorkflowTaskRepositoryDep
) -> WorkflowTask:
    """Return the WorkflowTask with the given ID, or HTTP 404 if missing."""
    task = await repo.get(task_id)
    if task is None:
        raise NotFoundError("WorkflowTask", task_id)
    return task


@router.patch("/{task_id}", response_model=WorkflowTask)
async def update_workflow_task(
    task_id: str,
    body: WorkflowTaskUpdate,
    repo: WorkflowTaskRepositoryDep,
    user_id: CurrentUserIdDep,
) -> WorkflowTask:
    """Apply a partial update to the WorkflowTask with the given ID."""
    return await repo.update(task_id, body, user_id=user_id)


@router.delete("/{task_id}")
async def delete_workflow_task(task_id: str, repo: WorkflowTaskRepositoryDep) -> None:
    """Delete the WorkflowTask with the given ID, raising 404 if it does not exist."""
    await repo.delete(task_id)
