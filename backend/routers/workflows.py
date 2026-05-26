"""CRUD endpoints for Workflow resources and the workflow execution action."""

import uuid

from fastapi import APIRouter

from dependencies import (
    AgentSkillRepositoryDep,
    ApiMetaDep,
    CurrentUserIdDep,
    PaginationDep,
    SkillManagerDep,
    WorkflowRepositoryDep,
    WorkflowSessionRepositoryDep,
)
from models.response import ApiResponse
from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=ApiResponse[Workflow], status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await repo.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.get("", response_model=ApiResponse[list[Workflow]])
async def list_workflows(
    repo: WorkflowRepositoryDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Workflow]]:
    items = await repo.list(limit=pagination.limit, offset=pagination.offset)
    return ApiResponse(meta=meta, data=items)


@router.get("/{workflow_id}", response_model=ApiResponse[Workflow])
async def get_workflow(
    workflow_id: str,
    repo: WorkflowRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await repo.get(workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow", workflow_id)
    return ApiResponse(meta=meta, data=workflow)


@router.patch("/{workflow_id}", response_model=ApiResponse[Workflow])
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await repo.update(workflow_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.delete("/{workflow_id}", response_model=ApiResponse[None])
async def delete_workflow(
    workflow_id: str,
    repo: WorkflowRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await repo.delete(workflow_id)
    return ApiResponse(meta=meta, data=None)


@router.post(
    "/{workflow_id}/execute",
    response_model=ApiResponse[WorkflowSession],
    status_code=201,
)
async def execute_workflow(
    workflow_id: str,
    workflows: WorkflowRepositoryDep,
    skills: AgentSkillRepositoryDep,
    skill_manager: SkillManagerDep,
    ws_repo: WorkflowSessionRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowSession]:
    """Create a WorkflowSession; the ADK session is created lazily on first agent call."""
    workflow = await workflows.get(workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow", workflow_id)
    skill = await skills.get(workflow.agent_skill_id)
    if skill is None:
        raise NotFoundError("AgentSkill", workflow.agent_skill_id)

    skill_dir = await skill_manager.ensure_cloned(skill)
    user = user_id or "user"
    session_id = str(uuid.uuid4())

    ws_create = WorkflowSessionCreate(
        session_id=session_id,
        workflow_name=workflow.name,
        workflow_prompt=workflow.prompt,
        workflow_description=workflow.description,
        agent_skill_id=skill.id,
        agent_skill_name=skill.name,
        agent_skill_repo_url=skill.repo_url,
        agent_skill_repo_path=skill.repo_path,
        skill_dir=str(skill_dir),
        user_id=user,
    )
    ws = await ws_repo.create(ws_create, workflow_id=workflow.id, user_id=user)
    return ApiResponse(meta=meta, data=ws)
