"""CRUD endpoints for AgentSkill resources."""

from fastapi import APIRouter

from dependencies import (
    AgentSkillRepositoryDep,
    ApiMetaDep,
    CurrentUserIdDep,
    PaginationDep,
)
from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from models.response import ApiResponse
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])


@router.post("", response_model=ApiResponse[AgentSkill], status_code=201)
async def create_agent_skill(
    body: AgentSkillCreate,
    repo: AgentSkillRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await repo.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=skill)


@router.get("", response_model=ApiResponse[list[AgentSkill]])
async def list_agent_skills(
    repo: AgentSkillRepositoryDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[AgentSkill]]:
    items = await repo.list(limit=pagination.limit, offset=pagination.offset)
    return ApiResponse(meta=meta, data=items)


@router.get("/{skill_id}", response_model=ApiResponse[AgentSkill])
async def get_agent_skill(
    skill_id: str,
    repo: AgentSkillRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await repo.get(skill_id)
    if skill is None:
        raise NotFoundError("AgentSkill", skill_id)
    return ApiResponse(meta=meta, data=skill)


@router.patch("/{skill_id}", response_model=ApiResponse[AgentSkill])
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    repo: AgentSkillRepositoryDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await repo.update(skill_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=skill)


@router.delete("/{skill_id}", response_model=ApiResponse[None])
async def delete_agent_skill(
    skill_id: str,
    repo: AgentSkillRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await repo.delete(skill_id)
    return ApiResponse(meta=meta, data=None)
