"""Use case service for Approval resources.

Wraps :class:`ApprovalRepository` with the business rules the router needs:
single-entity fetches raise :class:`NotFoundError` instead of returning ``None``,
so the router never repeats the null check.
"""

from collections.abc import Collection

from models.approval import Approval, ApprovalUpdate
from models.user import Role, User, has_any_role
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
        caller: User,
        caller_roles: Collection[str],
        sort: tuple[SortSpec, ...] | list[SortSpec] = (),
        filters: tuple[FilterSpec, ...] | list[FilterSpec] = (),
    ) -> list[Approval]:
        """Return approvals visible to the caller, defaulting to ``created_at`` descending.

        A super admin or admin sees every approval in the tenant; anyone else
        sees only approvals addressed to them or belonging to a
        WorkflowExecution they initiated.

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            caller: The authenticated user requesting the list.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            sort: Sort specifications.
            filters: Filter specifications.

        Returns:
            The matching approvals.
        """
        visible_to_user_id = (
            None
            if has_any_role(caller_roles, Role.super_admin, Role.admin)
            else caller.id
        )
        return await self._repo.list(
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
            visible_to_user_id=visible_to_user_id,
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
        """Resolve a pending approval to ``approved``, ``rejected``, or ``returned``.

        Only the approval's designated ``approver`` may resolve it — with no
        exception, not even for a super admin (or a plain admin) — so an
        approval request can be acted on solely by its addressee.

        Goes through :meth:`ApprovalRepository.resolve` rather than the generic
        ``update`` so the decision also stamps the server-managed ``decided_at``.

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
        return await self._repo.resolve(approval_id, data, user_id=acting_user.id)
