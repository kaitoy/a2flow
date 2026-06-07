"""AgentSkill repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError, ReferencedError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class AgentSkillRepository(Protocol):
    """Interface for AgentSkill persistence operations."""

    async def get(self, skill_id: str) -> AgentSkill | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[AgentSkill]: ...

    async def create(self, data: AgentSkillCreate, *, user_id: str) -> AgentSkill: ...

    async def update(
        self, skill_id: str, data: AgentSkillUpdate, *, user_id: str
    ) -> AgentSkill: ...

    async def delete(self, skill_id: str) -> None: ...

    async def exists(self, skill_id: str) -> bool: ...


class SqlAgentSkillRepository:
    """SQLModel-backed implementation of AgentSkillRepository.

    ``delete`` catches IntegrityError and re-raises it as ReferencedError when
    a skill is still referenced by one or more workflows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, skill_id: str) -> AgentSkill | None:
        return await self._db.get(AgentSkill, skill_id)

    async def exists(self, skill_id: str) -> bool:
        return (await self._db.get(AgentSkill, skill_id)) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[AgentSkill]:
        stmt = apply_filters(select(AgentSkill), AgentSkill, filters)
        stmt = apply_sort(
            stmt, AgentSkill, sort, default=[col(AgentSkill.created_at).desc()]
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: AgentSkillCreate, *, user_id: str) -> AgentSkill:
        skill = AgentSkill.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(skill)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(skill)
        return skill

    async def update(
        self, skill_id: str, data: AgentSkillUpdate, *, user_id: str
    ) -> AgentSkill:
        skill = await self._db.get(AgentSkill, skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)
        skill.sqlmodel_update(data.model_dump(exclude_unset=True))
        skill.updated_by = user_id
        self._db.add(skill)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
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
