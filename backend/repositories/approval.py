"""Approval repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalCreate, ApprovalUpdate
from models.user import User
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.workflow_session import WorkflowSessionRepository


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
    ) -> list[Approval]: ...

    async def create(self, data: ApprovalCreate, *, user_id: str) -> Approval: ...

    async def update(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval: ...

    async def exists(self, approval_id: str) -> bool: ...

    async def exists_for_approver(
        self, workflow_session_id: str, user_id: str
    ) -> bool: ...


class SqlApprovalRepository:
    """SQLModel-backed implementation of ApprovalRepository."""

    def __init__(
        self, session: AsyncSession, ws_repo: WorkflowSessionRepository
    ) -> None:
        """Store the async session and the WorkflowSession repository.

        The WorkflowSession repository is used to validate that the parent
        session exists before inserting an approval, producing a friendlier
        :class:`ForeignKeyViolationError` than the raw database constraint.
        """
        self._db = session
        self._ws_repo = ws_repo

    async def get(self, approval_id: str) -> Approval | None:
        """Return the Approval with the given ID, or ``None`` if missing."""
        return await self._db.get(Approval, approval_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Approval]:
        """Return Approvals, defaulting to ``created_at`` descending (newest first).

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications; defaults to ``created_at`` descending.
            filters: Filter specifications applied as a conjunction.

        Returns:
            The matching approvals.
        """
        stmt = apply_filters(select(Approval), Approval, filters)
        stmt = apply_sort(
            stmt,
            Approval,
            sort,
            default=[col(Approval.created_at).desc()],
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: ApprovalCreate, *, user_id: str) -> Approval:
        """Persist a new Approval, validating its workflow session exists.

        Args:
            data: The approval fields to insert.
            user_id: The acting user, recorded in the audit fields.

        Returns:
            The created approval.

        Raises:
            ForeignKeyViolationError: If ``workflow_session_id`` does not match an
                existing workflow session, or ``approver`` is set but does not
                match an existing user.
        """
        if await self._ws_repo.get(data.workflow_session_id) is None:
            raise ForeignKeyViolationError("WorkflowSession", data.workflow_session_id)
        if (
            data.approver is not None
            and await self._db.get(User, data.approver) is None
        ):
            raise ForeignKeyViolationError("User", data.approver)
        approval = Approval.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(approval)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(approval)
        return approval

    async def update(
        self, approval_id: str, data: ApprovalUpdate, *, user_id: str
    ) -> Approval:
        """Apply a partial update to an Approval, raising NotFoundError if missing."""
        approval = await self._db.get(Approval, approval_id)
        if approval is None:
            raise NotFoundError("Approval", approval_id)
        approval.sqlmodel_update(data.model_dump(exclude_unset=True))
        approval.updated_by = user_id
        self._db.add(approval)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(approval)
        return approval

    async def exists(self, approval_id: str) -> bool:
        """Return whether an Approval with the given ID exists."""
        stmt = select(Approval.id).where(Approval.id == approval_id).limit(1)
        result = await self._db.exec(stmt)
        return result.first() is not None

    async def exists_for_approver(self, workflow_session_id: str, user_id: str) -> bool:
        """Return whether the session has any Approval addressed to the user.

        Backs the workflow-session access check: a user designated as the
        approver of any approval in a session may view and participate in that
        session's shared chat.

        Args:
            workflow_session_id: Identifier of the workflow session.
            user_id: The candidate approver's user ID.

        Returns:
            ``True`` if at least one Approval in the session names the user as
            its ``approver``.
        """
        stmt = (
            select(Approval.id)
            .where(
                Approval.workflow_session_id == workflow_session_id,
                Approval.approver == user_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first() is not None
