"""CRUD endpoints for WorkflowTaskTemplate resources.

A WorkflowTaskTemplate is one step of a Workflow's pre-planned task list.
Listing the templates of a particular workflow is exposed on the Workflow
router as ``GET /workflows/{workflow_id}/task-templates``; this router focuses
on the create-and-act-on-a-single-template operations used by the admin plan
editor. Writes are developer-gated — templates belong to a workflow, not to a
per-user session, so no ownership rule applies.
"""

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    WorkflowTaskTemplateServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.user import Role
from models.workflow_task_template import (
    WorkflowTaskTemplateCreate,
    WorkflowTaskTemplateRead,
    WorkflowTaskTemplateUpdate,
)

router = APIRouter(prefix="/workflow-task-templates", tags=["workflow-task-templates"])

#: Route dependency gating template writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[WorkflowTaskTemplateRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_workflow_task_template(
    body: WorkflowTaskTemplateCreate,
    service: WorkflowTaskTemplateServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskTemplateRead]:
    """Create a new template belonging to the workflow named in ``body``."""
    template = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=template)


@router.get("/{template_id}", response_model=ApiResponse[WorkflowTaskTemplateRead])
async def get_workflow_task_template(
    template_id: str,
    service: WorkflowTaskTemplateServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskTemplateRead]:
    """Return the template with the given ID, or HTTP 404 if missing."""
    template = await service.get(template_id)
    return ApiResponse(meta=meta, data=template)


@router.patch(
    "/{template_id}",
    response_model=ApiResponse[WorkflowTaskTemplateRead],
    dependencies=_requires_developer,
)
async def update_workflow_task_template(
    template_id: str,
    body: WorkflowTaskTemplateUpdate,
    service: WorkflowTaskTemplateServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowTaskTemplateRead]:
    """Apply a partial update to the template with the given ID."""
    template = await service.update(template_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=template)


@router.delete(
    "/{template_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_workflow_task_template(
    template_id: str,
    service: WorkflowTaskTemplateServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete the template with the given ID, raising 404 if it does not exist."""
    await service.delete(template_id)
    return ApiResponse(meta=meta, data=None)
