"""Approval repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalCreate, ApprovalStatus, ApprovalUpdate
from models.user import User
from models.workflow_execution import WorkflowExecution
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.workflow_execution import WorkflowExecutionRepository


class ApprovalRepository(Protocol):
    """Interface for Approval persistence operations."""

    async def get(self, approval_id: str) -> Approval | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_to_user_id: str | None = None,
    ) -> list[Approval]: ...

    async def create(self, data: ApprovalCreate, *, user_id: str) -> Approval: ...

    async def update(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval: ...

    async def resolve(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval: ...

    async def exists(self, approval_id: str) -> bool: ...

    async def exists_for_approver(
        self, workflow_execution_id: str, user_id: str
    ) -> bool: ...

    async def get_for_task(self, workflow_task_id: str) -> Approval | None: ...


class SqlApprovalRepository:
    """SQLModel-backed implementation of ApprovalRepository."""

    def __init__(
        self,
        session: AsyncSession,
        execution_repo: WorkflowExecutionRepository,
        *,
        tenant_id: str,
    ) -> None:
        """Store the async session and the WorkflowExecution repository.

        The WorkflowExecution repository is used to validate that the parent
        session exists before inserting an approval, producing a friendlier
        :class:`ForeignKeyViolationError` than the raw database constraint.
        """
        self._db = session
        self._execution_repo = execution_repo
        self._tenant_id = tenant_id

    async def _get_scoped(self, approval_id: str) -> Approval | None:
        """Return the Approval with the given ID within the current tenant, or ``None``."""
        stmt = select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, approval_id: str) -> Approval | None:
        """Return the Approval with the given ID, or ``None`` if missing."""
        return await self._get_scoped(approval_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_to_user_id: str | None = None,
    ) -> list[Approval]:
        """Return Approvals, defaulting to ``created_at`` descending (newest first).

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications; defaults to ``created_at`` descending.
            filters: Filter specifications applied as a conjunction.
            visible_to_user_id: If given, restricts results to approvals
                addressed to this user, or belonging to a WorkflowExecution
                this user initiated; ``None`` (the default) returns every
                approval in the tenant, unscoped.

        Returns:
            The matching approvals.
        """
        stmt = select(Approval).where(Approval.tenant_id == self._tenant_id)
        if visible_to_user_id is not None:
            stmt = stmt.where(
                or_(
                    col(Approval.approver) == visible_to_user_id,
                    col(Approval.workflow_execution_id).in_(
                        select(WorkflowExecution.id).where(
                            col(WorkflowExecution.initiator_id) == visible_to_user_id,
                            WorkflowExecution.tenant_id == self._tenant_id,
                        )
                    ),
                )
            )
        stmt = apply_filters(stmt, Approval, filters, readable=Approval)
        stmt = apply_sort(
            stmt,
            Approval,
            sort,
            default=[col(Approval.created_at).desc()],
            readable=Approval,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: ApprovalCreate, *, user_id: str) -> Approval:
        """Persist a new Approval, validating its workflow execution exists.

        Args:
            data: The approval fields to insert.
            user_id: The acting user, recorded in the audit fields.

        Returns:
            The created approval.

        Raises:
            ForeignKeyViolationError: If ``workflow_execution_id`` does not match an
                existing workflow execution, or ``approver`` is set but does not
                match an existing user.
        """
        if await self._execution_repo.get(data.workflow_execution_id) is None:
            raise ForeignKeyViolationError(
                "WorkflowExecution", data.workflow_execution_id
            )
        if (
            data.approver is not None
            and await self._db.get(User, data.approver) is None
        ):
            raise ForeignKeyViolationError("User", data.approver)
        approval = Approval.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(approval)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(approval)
        return approval

    async def update(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval:
        """Apply a partial update to an Approval, raising NotFoundError if missing."""
        approval = await self._get_scoped(approval_id)
        if approval is None:
            raise NotFoundError("Approval", approval_id)
        approval.sqlmodel_update(data.model_dump(exclude_unset=True))
        approval.updated_by = user_id
        self._db.add(approval)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(approval)
        return approval

    async def resolve(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval:
        """Apply an approver's decision, stamping ``decided_at`` on the transition.

        Behaves like :meth:`update` but additionally maintains the server-managed
        ``decided_at`` column, which no client payload can write. The stamp lands
        exactly once — on the write that first moves the approval out of
        ``pending`` — so a later edit to the ``response`` comment leaves the
        recorded decision time alone, and the ``created_at`` -> ``decided_at``
        turnaround stays the approver's real one.

        Args:
            approval_id: Identifier of the approval to resolve.
            data: The new status and optional response comment.
            user_id: The acting user, recorded in the audit fields.

        Returns:
            The updated approval.

        Raises:
            NotFoundError: If the approval does not exist in this tenant.
        """
        approval = await self._get_scoped(approval_id)
        if approval is None:
            raise NotFoundError("Approval", approval_id)
        was_pending = approval.status == ApprovalStatus.pending
        approval.sqlmodel_update(data.model_dump(exclude_unset=True))
        if was_pending and approval.status != ApprovalStatus.pending:
            approval.decided_at = datetime.now(UTC)
        approval.updated_by = user_id
        self._db.add(approval)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(approval)
        return approval

    async def exists(self, approval_id: str) -> bool:
        """Return whether an Approval with the given ID exists."""
        stmt = (
            select(Approval.id)
            .where(Approval.id == approval_id, Approval.tenant_id == self._tenant_id)
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first() is not None

    async def exists_for_approver(
        self, workflow_execution_id: str, user_id: str
    ) -> bool:
        """Return whether the session has any Approval addressed to the user.

        Backs the workflow-execution access check: a user designated as the
        approver of any approval in a session may view and participate in that
        session's shared chat.

        Args:
            workflow_execution_id: Identifier of the workflow execution.
            user_id: The candidate approver's user ID.

        Returns:
            ``True`` if at least one Approval in the session names the user as
            its ``approver``.
        """
        stmt = (
            select(Approval.id)
            .where(
                Approval.workflow_execution_id == workflow_execution_id,
                Approval.approver == user_id,
                Approval.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first() is not None

    async def get_for_task(self, workflow_task_id: str) -> Approval | None:
        """Return the Approval linked to a WorkflowTask, or ``None`` if it has none.

        Backs WorkflowTaskService's designated-approver check on ``status``
        transitions. A task may in principle have more than one linked Approval
        (e.g. re-requested after a rejection); an unresolved (``pending``) one
        is preferred as the currently active request, falling back to the most
        recently created Approval otherwise.

        Args:
            workflow_task_id: Identifier of the WorkflowTask.

        Returns:
            The task's active linked Approval, or ``None`` if it has none.
        """
        stmt = (
            select(Approval)
            .where(
                Approval.workflow_task_id == workflow_task_id,
                Approval.tenant_id == self._tenant_id,
            )
            .order_by(col(Approval.created_at).desc())
        )
        result = await self._db.exec(stmt)
        approvals = list(result.all())
        for approval in approvals:
            if approval.status == ApprovalStatus.pending:
                return approval
        return approvals[0] if approvals else None
