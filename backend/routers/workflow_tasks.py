"""CRUD endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowExecution.
Listing the tasks of a particular execution is exposed on the WorkflowExecution
router as ``GET /workflow-executions/{session_id}/workflow-tasks``; this router
focuses on the create-and-act-on-a-single-task operations (enforced by
:class:`~services.workflow_task.WorkflowTaskService`). Reading a single task
(``GET``) is open to the parent execution's initiator, its designated
approvers, admins, and super admins; creating, updating, or deleting one
(``POST``/``PATCH``/``DELETE``) is restricted to the initiator, its designated
approvers, and super admins -- a plain admin cannot mutate tasks, even though
it can read them. Changing a task's ``status`` is further restricted when the
task has a linked Approval: only the execution initiator or that Approval's
designated approver may do so.
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    CurrentUserDep,
    EffectiveRolesDep,
    WorkflowTaskReadServiceDep,
    WorkflowTaskServiceDep,
)
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
    """Create a new WorkflowTask belonging to the execution named in ``body``.

    Restricted to the parent execution's initiator, its designated
    approvers, and super admins; a plain admin is rejected with HTTP 403.
    """
    task = await service.create(body, caller=caller)
    return ApiResponse(meta=meta, data=task)


@router.get("/{task_id}", response_model=ApiResponse[WorkflowTaskRead])
async def get_workflow_task(
    task_id: str,
    service: WorkflowTaskReadServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskRead]:
    """Return the WorkflowTask with the given ID, or HTTP 404 if missing.

    Open to the parent execution's initiator, its designated approvers,
    admins, and super admins.
    """
    task = await service.get(task_id, caller=caller, caller_roles=caller_roles)
    return ApiResponse(meta=meta, data=task)


@router.patch("/{task_id}", response_model=ApiResponse[WorkflowTaskRead])
async def update_workflow_task(
    task_id: str,
    body: WorkflowTaskUpdate,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskRead]:
    """Apply a partial update to the WorkflowTask with the given ID.

    Restricted to the parent execution's initiator, its designated
    approvers, and super admins; a plain admin is rejected with HTTP 403.
    """
    task = await service.update(task_id, body, caller=caller)
    return ApiResponse(meta=meta, data=task)


@router.delete("/{task_id}", response_model=ApiResponse[None])
async def delete_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete the WorkflowTask with the given ID, raising 404 if it does not exist.

    Restricted to the parent execution's initiator, its designated
    approvers, and super admins; a plain admin is rejected with HTTP 403.
    """
    await service.delete(task_id, caller=caller)
    return ApiResponse(meta=meta, data=None)
