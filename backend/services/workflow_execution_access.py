"""Access policy for workflow-execution-scoped operations.

A workflow execution's session (the chat it runs in) is shared between its
initiator and the designated approvers of its approvals (see README "Human
approval"). This policy exposes three methods, from broadest to narrowest:

- :meth:`assert_read_access` — participants (initiator, designated
  approvers), super admins, **and plain admins** (tenant-scoped, read-only).
  Backs every operation that only reads an execution or its workflow
  session: fetching the record, listing its tasks, and loading chat history.
- :meth:`assert_access` — participants and super admins only, **not**
  admins. Backs the operations that act on the execution: driving its
  agent, and creating/updating/deleting its tasks. An admin can see
  everything :meth:`assert_read_access` allows but cannot act on any of it.
- :meth:`assert_owner` — the execution's initiator or a super admin only.
  Backs deletion, deliberately stricter than either of the above.

All three reject unrelated third parties with :class:`ForbiddenError` (HTTP
403 ``FORBIDDEN``).

:meth:`assert_access` and :meth:`assert_owner` read the caller's **direct**
roles (``caller.roles``) rather than their effective ones. They only ever ask
about ``super_admin``, and a :class:`~models.user_group.UserGroup` can never
grant that role, so the two are equivalent here — and reading the column
keeps them correct even if that invariant were ever weakened.
:meth:`assert_read_access` additionally asks about ``admin``, which *can* be
granted through a group, so it takes the caller's **effective** roles
(``caller_roles``, see ``dependencies.auth.EffectiveRolesDep``) as an explicit
parameter instead — matching every other non-``super_admin`` role check in
the codebase (e.g. ``WorkflowService._assert_design_access``).

``WorkflowExecutionService.list`` and ``ApprovalService.list`` apply the same
initiator-or-designated-approver-or-super-admin-or-admin rule (also against
effective roles) to the collection endpoints (``GET /workflow-executions``,
``GET /approvals``), so a caller never sees a record in a list that
:meth:`assert_read_access` would then reject on the single-record read.
"""

from collections.abc import Collection

from models.user import Role, User, has_any_role
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

        The stricter of the two participant-based checks: unlike
        :meth:`assert_read_access`, a plain ``admin`` does **not** pass here.
        Used to authorize operations that act on the execution rather than
        merely read it -- driving its agent, and creating/updating/deleting
        its tasks.

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
        if has_any_role(caller.roles, Role.super_admin):
            return
        if await self._approvals.exists_for_approver(execution_id, caller.id):
            return
        raise ForbiddenError(
            "Only the execution initiator or a designated approver can access "
            "this workflow execution"
        )

    async def assert_read_access(
        self,
        execution_id: str,
        owner_id: str,
        caller: User,
        caller_roles: Collection[str],
    ) -> None:
        """Reject callers with no read access to the execution or its session.

        The read-only counterpart of :meth:`assert_access`: extends the same
        initiator-or-designated-approver-or-super-admin bypass to plain
        ``admin`` users, who may view (but, per :meth:`assert_access`, not
        drive or modify) any execution in their tenant. Backs the operations
        that only read the execution or its workflow session: fetching the
        record, listing its tasks, and loading chat history. The agent-run
        endpoint deliberately stays on the stricter :meth:`assert_access`
        instead of this method.

        Checks are ordered cheapest first, same as :meth:`assert_access`.

        Args:
            execution_id: Identifier of the workflow execution being read.
            owner_id: The execution initiator's user ID (``WorkflowExecution.initiator_id``).
            caller: The authenticated user performing the read.
            caller_roles: The caller's effective roles — direct grants plus
                everything inherited from their groups — since ``admin``,
                unlike ``super_admin``, can be group-granted.

        Raises:
            ForbiddenError: If the caller is not the execution's initiator,
                not a designated approver of any approval in the execution,
                and holds neither ``admin`` nor ``super_admin``.
        """
        if caller.id == owner_id:
            return
        if has_any_role(caller_roles, Role.super_admin, Role.admin):
            return
        if await self._approvals.exists_for_approver(execution_id, caller.id):
            return
        raise ForbiddenError(
            "Only the execution initiator, a designated approver, or an admin "
            "can access this workflow execution"
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
        if caller.id == owner_id or has_any_role(caller.roles, Role.super_admin):
            return
        raise ForbiddenError(
            "Only the execution initiator can delete this workflow execution"
        )
