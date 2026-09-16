"""Use case service for Approval resources.

Wraps :class:`ApprovalRepository` with the business rules the router needs:
single-entity fetches raise :class:`NotFoundError` instead of returning ``None``,
so the router never repeats the null check.
"""

from collections.abc import Collection

from models.approval import Approval, ApprovalRead, ApprovalStatus, ApprovalUpdate
from models.user import Role, User, has_any_role
from repositories.approval import ApprovalRepository
from repositories.exceptions import (
    ApprovalAlreadyResolvedError,
    ForbiddenError,
    NotFoundError,
)
from repositories.query import FilterSpec, SortSpec
from repositories.workflow_execution import WorkflowExecutionRepository
from services.approver_groups import ApproverGroupResolver
from services.mcp_tool_certificate import McpToolCertificateService


class ApprovalService:
    """Application service orchestrating Approval operations."""

    def __init__(
        self,
        repo: ApprovalRepository,
        approver_groups: ApproverGroupResolver,
        certificates: McpToolCertificateService,
        executions: WorkflowExecutionRepository,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Approval persistence, restricted to
                the approvals whose WorkflowExecution the caller's
                access-control tags admit (see :mod:`models.tag`). Every
                method here fetches through it first, so an approval under a
                run gated by a tag the caller's groups no longer carry reads
                as 404 -- whether browsing it or deciding it, and even for
                its own designated approver -- before
                :meth:`_assert_may_resolve` ever runs.
            approver_groups: Resolver for the groups the caller counts as an
                eligible approver for, backing group-addressed approvals.
            certificates: Issues the certificate that carries a granted
                approval's authority over the task's bound MCP tools.
            executions: Repository providing WorkflowExecution persistence,
                read here only for its tag attachments -- an approval has no
                tag join table of its own (see :mod:`models.tag`) and carries
                the same tags as the execution it belongs to.
        """
        self._repo = repo
        self._approver_groups = approver_groups
        self._certificates = certificates
        self._executions = executions

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        caller: User,
        caller_roles: Collection[str],
        sort: tuple[SortSpec, ...] | list[SortSpec] = (),
        filters: tuple[FilterSpec, ...] | list[FilterSpec] = (),
    ) -> list[ApprovalRead]:
        """Return approvals visible to the caller, defaulting to ``created_at`` descending.

        A super admin or admin sees every approval in the tenant; anyone else
        sees only approvals addressed to them -- directly, or through a group
        they may approve for -- or belonging to a WorkflowExecution they
        initiated.

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            caller: The authenticated user requesting the list.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            sort: Sort specifications.
            filters: Filter specifications.

        Returns:
            The matching approvals, each with its execution's tag ids
            attached. Excludes, in addition to the participant filter above,
            any approval whose WorkflowExecution is gated by an
            access-control tag the caller's groups do not hold -- see
            :attr:`_repo`.
        """
        if has_any_role(caller_roles, Role.super_admin, Role.admin):
            visible_to_user_id: str | None = None
            visible_to_group_ids: tuple[str, ...] = ()
        else:
            visible_to_user_id = caller.id
            visible_to_group_ids = await self._approver_groups.group_ids_for(
                caller, caller_roles
            )
        approvals = await self._repo.list(
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
            visible_to_user_id=visible_to_user_id,
            visible_to_group_ids=visible_to_group_ids,
        )
        tags_by_execution = await self._executions.tag_ids_for_many(
            [a.workflow_execution_id for a in approvals]
        )
        return [
            ApprovalRead.from_approval(
                a, tag_ids=tags_by_execution.get(a.workflow_execution_id, [])
            )
            for a in approvals
        ]

    async def _get(self, approval_id: str) -> Approval:
        """Return one approval, without projecting its execution's tag ids.

        Used internally by :meth:`resolve`, which needs the raw record for its
        status/destination checks but not the tag projection.

        Args:
            approval_id: Identifier of the approval to fetch.

        Returns:
            The matching approval.

        Raises:
            NotFoundError: If the approval does not exist, or it is hidden by
                an access-control tag the caller's groups do not hold.
        """
        approval = await self._repo.get(approval_id)
        if approval is None:
            raise NotFoundError("Approval", approval_id)
        return approval

    async def get(self, approval_id: str) -> ApprovalRead:
        """Return one approval, with its execution's tag ids attached.

        Args:
            approval_id: Identifier of the approval to fetch.

        Returns:
            The matching approval.

        Raises:
            NotFoundError: If the approval does not exist, or it is hidden by
                an access-control tag the caller's groups do not hold.
        """
        approval = await self._get(approval_id)
        tag_ids = await self._executions.tag_ids_for(approval.workflow_execution_id)
        return ApprovalRead.from_approval(approval, tag_ids=tag_ids)

    async def resolve(
        self, approval_id: str, data: ApprovalUpdate, *, acting_user: User
    ) -> Approval:
        """Resolve a pending approval to ``approved``, ``rejected``, or ``returned``.

        Only the approval's designated approver may resolve it -- with no
        exception, not even for a super admin (or a plain admin) -- so an
        approval request can be acted on solely by its addressee. For a
        group-addressed approval the addressee is the group: any member holding
        the ``approver`` role qualifies, and the first decision settles the
        request (see :class:`services.approver_groups.ApproverGroupResolver`).
        A legacy approval carrying no destination at all is resolvable by
        nobody, which is the behaviour it already had.

        A decision is final: submitting a second, different ``status`` for an
        already-decided approval raises
        :class:`~repositories.exceptions.ApprovalAlreadyResolvedError` rather
        than overwriting the first decision, since two members of the same
        group can genuinely race each other. Editing the ``response`` comment
        afterwards is still allowed.

        Goes through :meth:`ApprovalRepository.resolve` rather than the generic
        ``update`` so the decision also stamps the server-managed ``decided_at``
        and ``decided_by``.

        Granting an approval also issues the MCP tool certificates of the tasks
        it covers that are *already* underway (see
        :class:`services.mcp_tool_certificate.McpToolCertificateService`) --
        typically the task that asked for the go-ahead and is waiting on this
        very decision. The rest of the covered tasks are granted theirs as they
        start. Until a covered task holds one it cannot call any of its bound
        MCP tools, so this is the step that turns the decision into authority.
        Issuing is idempotent: editing the comment on an already-granted
        approval leaves the standing certificates alone rather than rotating
        them.

        Args:
            approval_id: Identifier of the approval to update.
            data: The new status and optional response comment.
            acting_user: The acting user; must be the approval's designated
                approver or an eligible member of its approver group, and is
                recorded in the audit fields and in ``decided_by``.

        Returns:
            The updated approval.

        Raises:
            NotFoundError: If the approval does not exist, or it is hidden by
                an access-control tag the caller's groups do not hold.
            ForbiddenError: If the acting user is not an eligible approver.
            ApprovalAlreadyResolvedError: If a decision is already recorded and
                this request would change it.
        """
        approval = await self._get(approval_id)
        await self._assert_may_resolve(approval, acting_user)
        if (
            data.status is not None
            and data.status != approval.status
            and approval.status != ApprovalStatus.pending
        ):
            raise ApprovalAlreadyResolvedError(approval_id, approval.status.value)
        resolved = await self._repo.resolve(approval_id, data, user_id=acting_user.id)
        await self._certificates.issue(resolved, user_id=acting_user.id)
        return resolved

    async def _assert_may_resolve(self, approval: Approval, caller: User) -> None:
        """Reject a caller who is not the approval's designated approver.

        Args:
            approval: The approval being resolved.
            caller: The authenticated user submitting the decision.

        Raises:
            ForbiddenError: If the caller is neither the designated user nor an
                eligible member of the designated group.
        """
        if approval.approver is not None:
            if approval.approver != caller.id:
                raise ForbiddenError(
                    "Only the designated approver can resolve this approval"
                )
            return
        if approval.approver_group_id is not None:
            eligible = await self._approver_groups.group_ids_for(caller)
            if approval.approver_group_id not in eligible:
                raise ForbiddenError(
                    "Only a member of the designated approver group holding the "
                    "approver role can resolve this approval"
                )
            return
        raise ForbiddenError("This approval has no designated approver")
