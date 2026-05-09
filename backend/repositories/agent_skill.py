from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from repositories.exceptions import NotFoundError, ReferencedError


class AgentSkillRepository(Protocol):
    async def get(self, skill_id: str) -> AgentSkill | None: ...

    async def list(self, *, limit: int, offset: int) -> list[AgentSkill]: ...

    async def create(self, data: AgentSkillCreate) -> AgentSkill: ...

    async def update(self, skill_id: str, data: AgentSkillUpdate) -> AgentSkill: ...

    async def delete(self, skill_id: str) -> None: ...

    async def exists(self, skill_id: str) -> bool: ...


class SqlAgentSkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, skill_id: str) -> AgentSkill | None:
        return await self._db.get(AgentSkill, skill_id)

    async def exists(self, skill_id: str) -> bool:
        return (await self._db.get(AgentSkill, skill_id)) is not None

    async def list(self, *, limit: int, offset: int) -> list[AgentSkill]:
        result = await self._db.exec(
            select(AgentSkill)
            .order_by(col(AgentSkill.created_at).desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    async def create(self, data: AgentSkillCreate) -> AgentSkill:
        skill = AgentSkill.model_validate(data.model_dump())
        self._db.add(skill)
        await self._db.commit()
        await self._db.refresh(skill)
        return skill

    async def update(self, skill_id: str, data: AgentSkillUpdate) -> AgentSkill:
        skill = await self._db.get(AgentSkill, skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)
        skill.sqlmodel_update(data.model_dump(exclude_unset=True))
        self._db.add(skill)
        await self._db.commit()
        await self._db.refresh(skill)
        return skill

    async def delete(self, skill_id: str) -> None:
        skill = await self._db.get(AgentSkill, skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)
        await self._db.delete(skill)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError(
                "AgentSkill is referenced by one or more workflows"
            ) from e
