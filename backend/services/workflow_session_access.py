"""Access policy for workflow-session-scoped operations.

A workflow session's chat is shared between its owner (the user who started
it) and the designated approvers of its approvals (see README "Human
approval"). This policy allows exactly those participants — plus super
admins — and rejects unrelated third parties with :class:`ForbiddenError`
(HTTP 403 ``FORBIDDEN``).
"""

from models.user import Role, User, has_role
from repositories import ApprovalRepository
from repositories.exceptions import ForbiddenError


class WorkflowSessionAccessPolicy:
    """Decides whether a user may operate on a given workflow session."""

    def __init__(self, approvals: ApprovalRepository) -> None:
        """Initialize the policy.

        Args:
            approvals: Repository used to look up whether the caller is a
                designated approver of any approval in the session.
        """
        self._approvals = approvals

    async def assert_access(self, ws_id: str, owner_id: str, caller: User) -> None:
        """Reject callers who are neither the owner, an approver, nor a super admin.

        Checks are ordered cheapest first: the owner (the common case — e.g.
        the chat page polling messages every 10 seconds) and super admins pass
        without any query; only other callers pay one indexed ``EXISTS`` query
        against the approvals table.

        Args:
            ws_id: Identifier of the workflow session being operated on.
            owner_id: The session owner's user ID (``WorkflowSession.user_id``).
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the session owner, not a
                designated approver of any approval in the session, and not a
                super admin.
        """
        if caller.id == owner_id:
            return
        if has_role(caller, Role.super_admin):
            return
        if await self._approvals.exists_for_approver(ws_id, caller.id):
            return
        raise ForbiddenError(
            "Only the session owner or a designated approver can access this "
            "workflow session"
        )

    def assert_owner(self, owner_id: str, caller: User) -> None:
        """Reject callers who are neither the owner nor a super admin.

        Used for destructive operations (deleting a session), which are
        deliberately stricter than the shared-chat access rule: a designated
        approver may participate in the chat but not delete it.

        Args:
            owner_id: The session owner's user ID (``WorkflowSession.user_id``).
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the session owner and not a
                super admin.
        """
        if caller.id == owner_id or has_role(caller, Role.super_admin):
            return
        raise ForbiddenError("Only the session owner can delete this workflow session")
