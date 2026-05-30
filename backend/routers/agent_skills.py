"""CRUD endpoints for AgentSkill resources."""

from fastapi import APIRouter

from dependencies import (
    AgentSkillServiceDep,
    ApiMetaDep,
    CurrentUserIdDep,
    PaginationDep,
)
from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from models.response import ApiResponse

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])


@router.post("", response_model=ApiResponse[AgentSkill], status_code=201)
async def create_agent_skill(
    body: AgentSkillCreate,
    service: AgentSkillServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await service.create(body, user_id=user_id)
    return ApiResponse(meta=meta, data=skill)


@router.get("", response_model=ApiResponse[list[AgentSkill]])
async def list_agent_skills(
    service: AgentSkillServiceDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[AgentSkill]]:
    items = await service.list(limit=pagination.limit, offset=pagination.offset)
    return ApiResponse(meta=meta, data=items)


@router.get("/{skill_id}", response_model=ApiResponse[AgentSkill])
async def get_agent_skill(
    skill_id: str,
    service: AgentSkillServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await service.get(skill_id)
    return ApiResponse(meta=meta, data=skill)


@router.patch("/{skill_id}", response_model=ApiResponse[AgentSkill])
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    service: AgentSkillServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await service.update(skill_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=skill)


@router.delete("/{skill_id}", response_model=ApiResponse[None])
async def delete_agent_skill(
    skill_id: str,
    service: AgentSkillServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(skill_id)
    return ApiResponse(meta=meta, data=None)
