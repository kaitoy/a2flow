"""Resolution of the user groups a caller may act as an approver for.

An :class:`~models.approval.Approval` addressed to a
:class:`~models.user_group.UserGroup` is resolvable by any member of that group
whose *effective* roles include :attr:`~models.user.Role.approver` -- see
``models/approval.py``. Four call sites need that same "which groups does this
caller count for" answer:

* :meth:`services.approval.ApprovalService.resolve` and
  :meth:`~services.approval.ApprovalService.list`,
* :class:`services.workflow_execution_access.WorkflowExecutionAccessPolicy`,
* :class:`services.workflow_task.WorkflowTaskService`'s status-change guard.

Keeping the rule here rather than duplicating it four times matters because the
role half is the security-relevant half: passing *raw* group memberships to
``exists_for_approver`` would hand the shared workflow-session chat to every
member of an approver group, including those who cannot approve anything. A
caller who does not hold ``approver`` resolves to **no** groups at all, so they
gain nothing from membership.

The role predicate deliberately mirrors
:func:`infrastructure.approval_tools._is_eligible_approver`, which decides who
an approval may be *addressed* to, so the address-time and act-time rules agree.
"""

from collections.abc import Collection

from models.user import Role, User, has_any_role
from repositories import EffectiveRoleRepository, UserGroupRepository


class ApproverGroupResolver:
    """Resolves the groups a caller counts as an eligible approver for."""

    def __init__(
        self,
        groups: UserGroupRepository,
        effective_roles: EffectiveRoleRepository,
    ) -> None:
        """Initialize the resolver.

        Args:
            groups: Repository used to read the caller's group memberships.
            effective_roles: Repository used to resolve the caller's inherited
                roles when the caller has not already done so.
        """
        self._groups = groups
        self._effective_roles = effective_roles

    async def group_ids_for(
        self, caller: User, caller_roles: Collection[str] | None = None
    ) -> tuple[str, ...]:
        """Return the groups whose approvals ``caller`` may act on.

        Returns an empty tuple for a caller who does not hold ``approver``,
        which is what stops a plain member of an approver group from gaining
        any access through the membership alone.

        Args:
            caller: The authenticated user being authorized.
            caller_roles: The caller's already-resolved effective roles, when
                the call site has them (``dependencies.auth.EffectiveRolesDep``).
                Omitting them costs one extra query, paid only on the paths
                that reach here -- a caller who is the execution's initiator or
                a super admin short-circuits before this is ever called.

        Returns:
            The ids of the caller's groups, or an empty tuple when they hold no
            ``approver`` role or belong to no group.
        """
        roles = (
            caller_roles
            if caller_roles is not None
            else await self._effective_roles.effective_roles_for_user(
                caller.id, caller.roles or []
            )
        )
        if not has_any_role(roles, Role.approver):
            return ()
        # A super_admin passes the role test through has_any_role's bypass, but
        # is platform-scoped and therefore never a member of any tenant-scoped
        # group, so this returns () for them -- see repositories.user_group's
        # _validate_members.
        return tuple(await self._groups.group_ids_for_user(caller.id))
