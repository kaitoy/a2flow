"""Access policy for workflow-execution-scoped operations.

A workflow execution's session (the chat it runs in) is shared between its
initiator and the designated approvers of its approvals (see README "Human
approval"). This policy allows exactly those participants — plus super
admins — and rejects unrelated third parties with :class:`ForbiddenError`
(HTTP 403 ``FORBIDDEN``).
"""

from models.user import Role, User, has_role
from repositories import ApprovalRepository
from repositories.exceptions import ForbiddenError


class WorkflowExecutionAccessPolicy:
    """Decides whether a user may operate on a given workflow execution."""

    def __init__(self, approvals: ApprovalRepository) -> None:
        """Initialize the policy.

        Args:
            approvals: Repository used to look up whether the caller is a
                designated approver of any approval in the execution.
        """
        self._approvals = approvals

    async def assert_access(
        self, execution_id: str, owner_id: str, caller: User
    ) -> None:
        """Reject callers who are neither the initiator, an approver, nor a super admin.

        Checks are ordered cheapest first: the initiator (the common case —
        e.g. the chat page polling messages every 10 seconds) and super admins pass
        without any query; only other callers pay one indexed ``EXISTS`` query
        against the approvals table.

        Args:
            execution_id: Identifier of the workflow execution being operated on.
            owner_id: The execution initiator's user ID (``WorkflowExecution.initiator_id``).
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the execution's initiator,
                not a designated approver of any approval in the execution,
                and not a super admin.
        """
        if caller.id == owner_id:
            return
        if has_role(caller, Role.super_admin):
            return
        if await self._approvals.exists_for_approver(execution_id, caller.id):
            return
        raise ForbiddenError(
            "Only the execution initiator or a designated approver can access "
            "this workflow execution"
        )

    def assert_owner(self, owner_id: str, caller: User) -> None:
        """Reject callers who are neither the initiator nor a super admin.

        Used for destructive operations (deleting an execution), which are
        deliberately stricter than the shared-session access rule: a designated
        approver may participate in the chat but not delete it.

        Args:
            owner_id: The execution initiator's user ID (``WorkflowExecution.initiator_id``).
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the execution's initiator
                and not a super admin.
        """
        if caller.id == owner_id or has_role(caller, Role.super_admin):
            return
        raise ForbiddenError(
            "Only the execution initiator can delete this workflow execution"
        )
