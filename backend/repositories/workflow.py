"""Workflow repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow import Workflow, WorkflowCreate, WorkflowStatus, WorkflowUpdate
from repositories._integrity import commit_or_translate_user_fk, is_foreign_key_error
from repositories.agent_skill import AgentSkillRepository
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class WorkflowRepository(Protocol):
    """Interface for Workflow persistence operations."""

    async def get(self, workflow_id: str) -> Workflow | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Workflow]: ...

    async def create(self, data: WorkflowCreate, *, user_id: str) -> Workflow: ...

    async def update(
        self, workflow_id: str, data: WorkflowUpdate, *, user_id: str
    ) -> Workflow: ...

    async def set_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
        *,
        generation_error: str | None = None,
        description: str | None = None,
        user_id: str,
    ) -> Workflow: ...

    async def delete(self, workflow_id: str) -> None: ...


class SqlWorkflowRepository:
    """SQLModel-backed implementation of WorkflowRepository.

    Validates that the referenced ``agent_skill_id`` exists before creating or
    updating a workflow, raising ForeignKeyViolationError if it does not.
    """

    def __init__(
        self, session: AsyncSession, skills: AgentSkillRepository, *, tenant_id: str
    ) -> None:
        self._db = session
        self._skills = skills
        self._tenant_id = tenant_id

    async def _get_scoped(self, workflow_id: str) -> Workflow | None:
        stmt = select(Workflow).where(
            Workflow.id == workflow_id, Workflow.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, workflow_id: str) -> Workflow | None:
        return await self._get_scoped(workflow_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Workflow]:
        stmt = select(Workflow).where(Workflow.tenant_id == self._tenant_id)
        stmt = apply_filters(stmt, Workflow, filters)
        stmt = apply_sort(
            stmt, Workflow, sort, default=[col(Workflow.created_at).desc()]
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: WorkflowCreate, *, user_id: str) -> Workflow:
        """Create a new Workflow, raising UniqueViolationError on duplicate name."""
        if not await self._skills.exists(data.agent_skill_id):
            raise ForeignKeyViolationError("AgentSkill", data.agent_skill_id)
        workflow = Workflow.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(workflow)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("Workflow", "name", data.name) from e
        await self._db.refresh(workflow)
        return workflow

    async def update(
        self, workflow_id: str, data: WorkflowUpdate, *, user_id: str
    ) -> Workflow:
        """Apply a partial update, raising NotFoundError or UniqueViolationError."""
        workflow = await self._get_scoped(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        update = data.model_dump(exclude_unset=True)
        workflow.sqlmodel_update(update)
        workflow.updated_by = user_id
        self._db.add(workflow)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "Workflow", "name", str(update.get("name", ""))
            ) from e
        await self._db.refresh(workflow)
        return workflow

    async def set_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
        *,
        generation_error: str | None = None,
        description: str | None = None,
        user_id: str,
    ) -> Workflow:
        """Set the server-managed lifecycle fields of a workflow.

        ``status`` and ``generation_error`` are absent from ``WorkflowUpdate``
        so they cannot be written through the API; the generation job and the
        publish use case go through this method instead. ``generation_error``
        is always overwritten (a successful transition clears a stale error).
        ``description`` is only written when non-``None`` — the callers pass
        the freshly generated conversation summary here so it lands in the same
        commit as the status change.

        Args:
            workflow_id: Identifier of the workflow to update.
            status: The new lifecycle status.
            generation_error: Failure reason to record, or ``None`` to clear.
            description: New summary description, or ``None`` to keep as is.
            user_id: ID of the acting user recorded on ``updated_by``.

        Returns:
            The updated workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        workflow = await self._get_scoped(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        workflow.status = status
        workflow.generation_error = generation_error
        if description is not None:
            workflow.description = description
        workflow.updated_by = user_id
        self._db.add(workflow)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(workflow)
        return workflow

    async def delete(self, workflow_id: str) -> None:
        workflow = await self._get_scoped(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        await self._db.delete(workflow)
        await self._db.commit()
