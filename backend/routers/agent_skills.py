from fastapi import APIRouter, HTTPException

from dependencies import AgentSkillRepositoryDep
from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from repositories.exceptions import NotFoundError, ReferencedError

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])


@router.post("", response_model=AgentSkill, status_code=201)
async def create_agent_skill(
    body: AgentSkillCreate,
    repo: AgentSkillRepositoryDep,
) -> AgentSkill:
    return await repo.create(body)


@router.get("", response_model=list[AgentSkill])
async def list_agent_skills(
    repo: AgentSkillRepositoryDep,
    limit: int = 20,
    offset: int = 0,
) -> list[AgentSkill]:
    return await repo.list(limit=limit, offset=offset)


@router.get("/{skill_id}", response_model=AgentSkill)
async def get_agent_skill(skill_id: str, repo: AgentSkillRepositoryDep) -> AgentSkill:
    skill = await repo.get(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Agent skill not found")
    return skill


@router.patch("/{skill_id}", response_model=AgentSkill)
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    repo: AgentSkillRepositoryDep,
) -> AgentSkill:
    try:
        return await repo.update(skill_id, body)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Agent skill not found") from e


@router.delete("/{skill_id}", status_code=204)
async def delete_agent_skill(skill_id: str, repo: AgentSkillRepositoryDep) -> None:
    try:
        await repo.delete(skill_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Agent skill not found") from e
    except ReferencedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
