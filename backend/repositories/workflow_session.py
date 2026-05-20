from typing import Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from repositories.exceptions import NotFoundError


class WorkflowSessionRepository(Protocol):
    async def get(self, ws_id: str) -> WorkflowSession | None: ...

    async def create(
        self, data: WorkflowSessionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowSession: ...

    async def delete(self, ws_id: str) -> None: ...


class SqlWorkflowSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, ws_id: str) -> WorkflowSession | None:
        return await self._db.get(WorkflowSession, ws_id)

    async def create(
        self, data: WorkflowSessionCreate, *, workflow_id: str, user_id: str
    ) -> WorkflowSession:
        ws = WorkflowSession.model_validate(
            {
                **data.model_dump(),
                "workflow_id": workflow_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(ws)
        await self._db.commit()
        await self._db.refresh(ws)
        return ws

    async def delete(self, ws_id: str) -> None:
        ws = await self._db.get(WorkflowSession, ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        await self._db.delete(ws)
        await self._db.commit()
