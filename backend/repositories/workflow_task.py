"""WorkflowTask repository: Protocol interface and SQLModel-backed implementation."""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_task import WorkflowTask, WorkflowTaskCreate, WorkflowTaskUpdate
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from repositories.workflow_session import WorkflowSessionRepository


class WorkflowTaskRepository(Protocol):
    """Interface for WorkflowTask persistence operations."""

    async def get(self, task_id: str) -> WorkflowTask | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_session_id: str | None = None,
    ) -> list[WorkflowTask]: ...

    async def create(
        self, data: WorkflowTaskCreate, *, user_id: str
    ) -> WorkflowTask: ...

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, user_id: str
    ) -> WorkflowTask: ...

    async def delete(self, task_id: str) -> None: ...


class SqlWorkflowTaskRepository:
    """SQLModel-backed implementation of WorkflowTaskRepository.

    Validates that the referenced ``workflow_session_id`` exists before creating
    a task, raising ForeignKeyViolationError if it does not. Updates do not
    re-validate parent existence because ``WorkflowTaskUpdate`` does not allow
    changing ``workflow_session_id``.
    """

    def __init__(
        self, session: AsyncSession, ws_repo: WorkflowSessionRepository
    ) -> None:
        """Store the SQLModel session and the WorkflowSession repository for FK checks."""
        self._db = session
        self._ws = ws_repo

    async def get(self, task_id: str) -> WorkflowTask | None:
        """Return the WorkflowTask with the given ID, or ``None`` if missing."""
        return await self._db.get(WorkflowTask, task_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        workflow_session_id: str | None = None,
    ) -> list[WorkflowTask]:
        """Return WorkflowTasks ordered by ``position`` then ``created_at``.

        When ``workflow_session_id`` is supplied, only tasks belonging to that
        session are returned.
        """
        stmt = select(WorkflowTask)
        if workflow_session_id is not None:
            stmt = stmt.where(WorkflowTask.workflow_session_id == workflow_session_id)
        stmt = (
            stmt.order_by(
                col(WorkflowTask.position).asc(),
                col(WorkflowTask.created_at).asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.exec(stmt)
        return list(result.all())

    async def create(self, data: WorkflowTaskCreate, *, user_id: str) -> WorkflowTask:
        """Create a new WorkflowTask after validating the parent session exists."""
        if await self._ws.get(data.workflow_session_id) is None:
            raise ForeignKeyViolationError("WorkflowSession", data.workflow_session_id)
        task = WorkflowTask.model_validate(
            {
                **data.model_dump(),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(task)
        await self._db.commit()
        await self._db.refresh(task)
        return task

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, user_id: str
    ) -> WorkflowTask:
        """Apply a partial update to an existing WorkflowTask.

        ``workflow_session_id`` is not part of ``WorkflowTaskUpdate`` so no
        foreign-key re-validation is needed here.
        """
        task = await self._db.get(WorkflowTask, task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        task.sqlmodel_update(data.model_dump(exclude_unset=True))
        task.updated_by = user_id
        self._db.add(task)
        await self._db.commit()
        await self._db.refresh(task)
        return task

    async def delete(self, task_id: str) -> None:
        """Delete the WorkflowTask with the given ID, raising NotFoundError if missing."""
        task = await self._db.get(WorkflowTask, task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        await self._db.delete(task)
        await self._db.commit()
