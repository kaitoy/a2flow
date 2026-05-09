from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from repositories.agent_skill import AgentSkillRepository
from repositories.exceptions import ForeignKeyViolationError, NotFoundError


class WorkflowRepository(Protocol):
    async def get(self, workflow_id: str) -> Workflow | None: ...

    async def list(self, *, limit: int, offset: int) -> list[Workflow]: ...

    async def create(self, data: WorkflowCreate) -> Workflow: ...

    async def update(self, workflow_id: str, data: WorkflowUpdate) -> Workflow: ...

    async def delete(self, workflow_id: str) -> None: ...


class SqlWorkflowRepository:
    def __init__(self, session: AsyncSession, skills: AgentSkillRepository) -> None:
        self._db = session
        self._skills = skills

    async def get(self, workflow_id: str) -> Workflow | None:
        return await self._db.get(Workflow, workflow_id)

    async def list(self, *, limit: int, offset: int) -> list[Workflow]:
        result = await self._db.exec(
            select(Workflow)
            .order_by(col(Workflow.created_at).desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    async def create(self, data: WorkflowCreate) -> Workflow:
        if not await self._skills.exists(data.agent_skill_id):
            raise ForeignKeyViolationError("AgentSkill", data.agent_skill_id)
        workflow = Workflow.model_validate(data.model_dump())
        self._db.add(workflow)
        await self._db.commit()
        await self._db.refresh(workflow)
        return workflow

    async def update(self, workflow_id: str, data: WorkflowUpdate) -> Workflow:
        workflow = await self._db.get(Workflow, workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        update = data.model_dump(exclude_unset=True)
        new_skill_id = update.get("agent_skill_id")
        if new_skill_id is not None and not await self._skills.exists(new_skill_id):
            raise ForeignKeyViolationError("AgentSkill", new_skill_id)
        workflow.sqlmodel_update(update)
        workflow.updated_at = datetime.now(UTC)
        self._db.add(workflow)
        await self._db.commit()
        await self._db.refresh(workflow)
        return workflow

    async def delete(self, workflow_id: str) -> None:
        workflow = await self._db.get(Workflow, workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        await self._db.delete(workflow)
        await self._db.commit()
