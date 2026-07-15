"""Use case service for Approval resources.

Wraps :class:`ApprovalRepository` with the business rules the router needs:
single-entity fetches raise :class:`NotFoundError` instead of returning ``None``,
so the router never repeats the null check.
"""

from models.approval import Approval, ApprovalUpdate
from models.user import User
from repositories import ApprovalRepository
from repositories.exceptions import ForbiddenError, NotFoundError
from repositories.query import FilterSpec, SortSpec


class ApprovalService:
    """Application service orchestrating Approval operations."""

    def __init__(self, repo: ApprovalRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Approval persistence.
        """
        self._repo = repo

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: tuple[SortSpec, ...] | list[SortSpec] = (),
        filters: tuple[FilterSpec, ...] | list[FilterSpec] = (),
    ) -> list[Approval]:
        """Return approvals, defaulting to ``created_at`` descending.

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications.
            filters: Filter specifications.

        Returns:
            The matching approvals.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def get(self, approval_id: str) -> Approval:
        """Return one approval.

        Args:
            approval_id: Identifier of the approval to fetch.

        Returns:
            The matching approval.

        Raises:
            NotFoundError: If the approval does not exist.
        """
        approval = await self._repo.get(approval_id)
        if approval is None:
            raise NotFoundError("Approval", approval_id)
        return approval

    async def resolve(
        self, approval_id: str, data: ApprovalUpdate, *, acting_user: User
    ) -> Approval:
        """Resolve a pending approval to ``approved`` or ``rejected``.

        Only the approval's designated ``approver`` may resolve it — with no
        exception, not even for a super admin — so an approval request can be
        acted on solely by its addressee.

        Args:
            approval_id: Identifier of the approval to update.
            data: The new status and optional response comment.
            acting_user: The acting user; must be the approval's ``approver``,
                and is recorded in the audit fields.

        Returns:
            The updated approval.

        Raises:
            NotFoundError: If the approval does not exist.
            ForbiddenError: If the acting user is not the designated approver.
        """
        approval = await self.get(approval_id)
        if approval.approver != acting_user.id:
            raise ForbiddenError(
                "Only the designated approver can resolve this approval"
            )
        return await self._repo.update(approval_id, data, user_id=acting_user.id)
