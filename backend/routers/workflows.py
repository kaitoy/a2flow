"""Endpoints for Workflow resources: reads, updates, publication, and execution.

Workflows are not created here — they are born from
``POST /agent-skills/{skill_id}/workflows`` ("Generate workflow", see
``routers/agent_skills.py``), which registers a draft and generates its task
templates in the background. This router covers everything after that:
inspecting a workflow and its templates, editing name/description, opening its
planning session, publishing it, and executing it.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    PlanningSessionServiceDep,
    SortDep,
    WorkflowPlanningServiceDep,
    WorkflowServiceDep,
    WorkflowTaskTemplateServiceDep,
    require_roles,
)
from models.planning_session import PlanningSession
from models.response import ApiResponse
from models.user import Role
from models.workflow import Workflow, WorkflowUpdate
from models.workflow_session import WorkflowSession
from models.workflow_task_template import WorkflowTaskTemplateRead

router = APIRouter(prefix="/workflows", tags=["workflows"])

#: Route dependency gating workflow writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]

#: Route dependency gating workflow execution behind the ``requester`` role.
_requires_requester = [Depends(require_roles(Role.requester))]


@router.get("", response_model=ApiResponse[list[Workflow]])
async def list_workflows(
    service: WorkflowServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Workflow]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{workflow_id}", response_model=ApiResponse[Workflow])
async def get_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.get(workflow_id)
    return ApiResponse(meta=meta, data=workflow)


@router.get(
    "/{workflow_id}/task-templates",
    response_model=ApiResponse[list[WorkflowTaskTemplateRead]],
)
async def list_workflow_task_templates(
    workflow_id: str,
    service: WorkflowTaskTemplateServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskTemplateRead]]:
    """Return the task templates belonging to the given Workflow.

    Raises HTTP 404 (``NotFoundError``) if the workflow does not exist, so
    callers can distinguish "no such workflow" from "workflow has no
    templates".
    """
    items = await service.list_for_workflow(
        workflow_id,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get(
    "/{workflow_id}/planning-session",
    response_model=ApiResponse[PlanningSession],
)
async def get_workflow_planning_session(
    workflow_id: str,
    service: PlanningSessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[PlanningSession]:
    """Return the planning session of the given Workflow.

    Every generated workflow has exactly one; raises HTTP 404 when the
    workflow (or its session) does not exist.
    """
    ps = await service.get_for_workflow(workflow_id)
    return ApiResponse(meta=meta, data=ps)


@router.patch(
    "/{workflow_id}",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.update(workflow_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.delete(
    "/{workflow_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(workflow_id)
    return ApiResponse(meta=meta, data=None)


@router.post(
    "/{workflow_id}/publish",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def publish_workflow(
    workflow_id: str,
    service: WorkflowPlanningServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Publish a workflow, making it executable.

    Re-summarizes the planning conversation into the workflow's description.
    Raises HTTP 409 (``WORKFLOW_NOT_RUNNABLE``) while generation is in flight
    or when the workflow has no task templates.
    """
    workflow = await service.publish(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.post(
    "/{workflow_id}/execute",
    response_model=ApiResponse[WorkflowSession],
    status_code=201,
    dependencies=_requires_requester,
)
async def execute_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowSession]:
    """Create a WorkflowSession pre-filled with the workflow's task templates.

    Only ``published`` workflows can be executed (HTTP 409
    ``WORKFLOW_NOT_RUNNABLE`` otherwise). The ADK session is created lazily on
    the first agent call, which starts executing immediately.
    """
    ws = await service.execute(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=ws)
