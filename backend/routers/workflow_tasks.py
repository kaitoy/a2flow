"""Read and status-update endpoints for WorkflowTask resources.

A WorkflowTask is a single actionable item belonging to a WorkflowExecution.
Listing the tasks of a particular execution is exposed on the WorkflowExecution
router as ``GET /workflow-executions/{session_id}/workflow-tasks``; most of
this router focuses on acting on a single task (enforced by
:class:`~services.workflow_task.WorkflowTaskService`). The exception is the
flat ``GET /workflow-tasks`` below, an ``admin``-gated surface spanning every
execution in the tenant -- it exists so the tenant-wide MCP audit trails
(``GET /mcp-tool-invocations``, ``GET /mcp-tool-certificates``) can resolve a
row's ``workflowTaskId`` to its ``title`` with one batched ``id:in:`` lookup,
the same way ``GET /workflow-executions`` and ``GET /approvals`` already let
those trails resolve their own execution/approval ids.

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

from fastapi import APIRouter, Depends

from dependencies.auth import CurrentUserDep, EffectiveRolesDep
from dependencies.authz import require_roles
from dependencies.context import ApiMetaDep, FilterDep, PaginationDep, SortDep
from dependencies.service import WorkflowTaskServiceDep
from models.response import ApiResponse
from models.user import Role
from models.workflow_task import (
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)

router = APIRouter(prefix="/workflow-tasks", tags=["workflow-tasks"])

#: Route dependency gating the tenant-wide flat list behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get(
    "",
    response_model=ApiResponse[list[WorkflowTaskRead]],
    dependencies=_requires_admin,
)
async def list_workflow_tasks(
    service: WorkflowTaskServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskRead]]:
    """Return WorkflowTask records across every execution in the acting tenant.

    Unlike ``GET /{task_id}`` below, this does not check per-execution
    participant access -- it authorizes by role alone, admin or super admin,
    matching the other tenant-wide MCP audit surfaces. A platform-scoped
    super admin may select ``X-Tenant-Id: __all__`` to list across every
    tenant at once. Defaults to ``createdAt`` then ``id`` ascending; the
    typical caller filters with ``q=id:in:<comma-separated ids>`` to resolve a
    batch of task ids to their titles.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


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
