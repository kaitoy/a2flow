"""CRUD endpoints for AgentSkill resources."""

from fastapi import APIRouter

from dependencies import AgentSkillRepositoryDep, CurrentUserIdDep, PaginationDep
from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])


@router.post("", response_model=AgentSkill, status_code=201)
async def create_agent_skill(
    body: AgentSkillCreate,
    repo: AgentSkillRepositoryDep,
    user_id: CurrentUserIdDep,
) -> AgentSkill:
    return await repo.create(body, user_id=user_id)


@router.get("", response_model=list[AgentSkill])
async def list_agent_skills(
    repo: AgentSkillRepositoryDep,
    pagination: PaginationDep,
) -> list[AgentSkill]:
    return await repo.list(limit=pagination.limit, offset=pagination.offset)


@router.get("/{skill_id}", response_model=AgentSkill)
async def get_agent_skill(skill_id: str, repo: AgentSkillRepositoryDep) -> AgentSkill:
    skill = await repo.get(skill_id)
    if skill is None:
        raise NotFoundError("AgentSkill", skill_id)
    return skill


@router.patch("/{skill_id}", response_model=AgentSkill)
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    repo: AgentSkillRepositoryDep,
    user_id: CurrentUserIdDep,
) -> AgentSkill:
    return await repo.update(skill_id, body, user_id=user_id)


@router.delete("/{skill_id}")
async def delete_agent_skill(skill_id: str, repo: AgentSkillRepositoryDep) -> None:
    await repo.delete(skill_id)
