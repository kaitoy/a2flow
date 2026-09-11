"""Read and status-update endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowExecution.
Listing the tasks of a particular execution is exposed on the WorkflowExecution
router as ``GET /workflow-executions/{session_id}/workflow-tasks``; this router
focuses on acting on a single task (enforced by
:class:`~services.workflow_task.WorkflowTaskService`).

A run's task list is fixed at execute time (copied from the workflow's
published templates), so there is no create or delete endpoint here, and
``PATCH`` touches only ``status`` / ``error_kind`` / ``error_message`` -- a
task's title, description, dependency edges and tool bindings cannot be changed
once it exists. Reading a single task (``GET``) is open to the parent
execution's initiator, its designated approvers, admins, and super admins;
updating one (``PATCH``) is restricted to the initiator, its designated
approvers, and super admins -- a plain admin cannot mutate tasks, even though
it can read them. Changing a task's ``status`` is further restricted when the
task has a linked Approval: only the execution initiator or that Approval's
designated approver may do so.
"""

from fastapi import APIRouter

from dependencies.auth import CurrentUserDep, EffectiveRolesDep
from dependencies.context import ApiMetaDep
from dependencies.service import WorkflowTaskServiceDep
from models.response import ApiResponse
from models.workflow_task import (
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)

router = APIRouter(prefix="/workflow-tasks", tags=["workflow-tasks"])


@router.get("/{task_id}", response_model=ApiResponse[WorkflowTaskRead])
async def get_workflow_task(
    task_id: str,
    service: WorkflowTaskServiceDep,
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

    Only ``status`` / ``error_kind`` / ``error_message`` are updatable; any
    other field in the body is ignored. Restricted to the parent execution's
    initiator, its designated approvers, and super admins; a plain admin is
    rejected with HTTP 403.
    """
    task = await service.update(task_id, body, caller=caller)
    return ApiResponse(meta=meta, data=task)
