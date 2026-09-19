"""Access policy for workflow-execution-scoped operations.

A workflow execution's session (the chat it runs in) is shared between its
initiator and the designated approvers of its approvals (see README "Human
approval"). "Designated approver" covers both destinations an approval can
have: the single user named in ``Approval.approver``, and every member of the
group named in ``Approval.approver_group_id`` who holds the ``approver`` role.
That second half is resolved by
:class:`services.approver_groups.ApproverGroupResolver` and is deliberately
role-filtered -- passing raw group memberships to
``ApprovalRepository.exists_for_approver`` would share the chat with members
who cannot approve anything.

Note that this makes participation *mutable*: adding someone to an approver
group grants them access to every execution that group has ever been asked to
approve, and removing them revokes it, both on the next request. That follows
directly from "any member of the group can resolve it" -- resolving is what the
chat access exists to enable.

This policy exposes two methods, from broadest to narrowest:

- :meth:`assert_read_access` — participants (initiator, designated
  approvers), super admins, **and plain admins** (tenant-scoped, read-only).
  Backs every operation that only reads an execution or its workflow
  session: fetching the record, listing its tasks, and loading chat history.
- :meth:`assert_access` — participants and super admins only, **not**
  admins. Backs the operations that act on the execution: driving its
  agent, and creating/updating/deleting its tasks. An admin can see
  everything :meth:`assert_read_access` allows but cannot act on any of it.

Deletion is authorized separately, by the router's
``require_roles(Role.admin)`` route dependency rather than by this policy —
see ``routers/workflow_executions.py``.

Both reject unrelated third parties with :class:`ForbiddenError` (HTTP
403 ``FORBIDDEN``).

:meth:`assert_access` reads the caller's **direct** roles (``caller.roles``)
rather than their effective ones. It only ever asks about ``super_admin``,
and a :class:`~models.user_group.UserGroup` can never grant that role, so the
two are equivalent here — and reading the column keeps it correct even if
that invariant were ever weakened.
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

Passing :meth:`assert_access` admits a caller to the chat, not to every task in
it. A designated approver's part is their approval; the input forms the agent
renders for the other steps are the initiator's to fill in, so
:func:`assert_may_answer_surfaces` rejects an A2UI form submission from anyone
else -- super admins included, matching ``ApprovalService.resolve``.
"""

import json
from collections.abc import Collection, Sequence

from ag_ui.core import Message, ToolMessage

from models.user import Role, User, has_any_role
from repositories.approval import ApprovalRepository
from repositories.exceptions import ForbiddenError
from services.approver_groups import ApproverGroupResolver
from services.session_attribution import RENDER_ACK_RESPONSE

#: The ``render_approval`` results the frontend sends. The decision itself is
#: recorded through ``PATCH /approvals/{id}``, which has its own approver check;
#: this result only tells the agent to carry on.
_APPROVAL_DECISIONS = frozenset({"approved", "rejected", "returned"})


def _is_render_ack(content: str) -> bool:
    """Return whether a tool result is the no-op ``render_a2ui`` acknowledgement."""
    try:
        return bool(json.loads(content) == RENDER_ACK_RESPONSE)
    except ValueError:
        return False


def assert_may_answer_surfaces(
    messages: Sequence[Message], *, caller_id: str, initiator_id: str
) -> None:
    """Reject A2UI form submissions from anyone but the execution initiator.

    A non-initiator's run may carry only two kinds of tool result: the no-op
    render acknowledgement every run flushes for the still-pending surfaces,
    and a ``render_approval`` decision. Anything else answering a client tool
    call is the ``{"status": "action", ...}`` payload of a submitted form.

    The check is by content rather than by matching ``tool_call_id`` against
    the session's ``render_a2ui`` calls: ADK can hand a long-running client
    tool a different id in the persisted event than in the streamed one, so
    the id the frontend echoes back is not reliably in the session.

    Args:
        messages: The run's incoming messages, system messages already stripped.
        caller_id: The authenticated user driving the run.
        initiator_id: ``WorkflowExecution.initiator_id``.

    Raises:
        ForbiddenError: If ``caller_id`` is not the initiator and ``messages``
            contain a tool result that is neither a render acknowledgement nor
            an approval decision.
    """
    if caller_id == initiator_id:
        return
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.content in _APPROVAL_DECISIONS or _is_render_ack(message.content):
            continue
        raise ForbiddenError(
            "Only the execution initiator can submit a form the agent rendered"
        )


class WorkflowExecutionAccessPolicy:
    """Decides whether a user may operate on a given workflow execution."""

    def __init__(
        self,
        approvals: ApprovalRepository,
        approver_groups: ApproverGroupResolver,
    ) -> None:
        """Initialize the policy.

        Args:
            approvals: Repository used to look up whether the caller is a
                designated approver of any approval in the execution.
            approver_groups: Resolver for the groups the caller counts as an
                eligible approver for, so an approval addressed to a group
                admits its eligible members the same way a directly addressed
                one admits its named user.
        """
        self._approvals = approvals
        self._approver_groups = approver_groups

    async def approver_group_ids(
        self, caller: User, caller_roles: Collection[str] | None = None
    ) -> tuple[str, ...]:
        """Return the groups whose approvals ``caller`` may act on.

        Exposed so the collection endpoints can apply the same rule as the
        single-record checks: ``WorkflowExecutionService.list`` needs the ids to
        build its visibility filter, and duplicating the resolver there would
        let the two drift apart.

        Args:
            caller: The authenticated user being authorized.
            caller_roles: The caller's already-resolved effective roles, when
                available; omitting them costs one extra query.

        Returns:
            The caller's eligible approver group ids, empty when they hold no
            ``approver`` role.
        """
        return await self._approver_groups.group_ids_for(caller, caller_roles)

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
        if await self._approvals.exists_for_approver(
            execution_id,
            caller.id,
            group_ids=await self._approver_groups.group_ids_for(caller),
        ):
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
        if await self._approvals.exists_for_approver(
            execution_id,
            caller.id,
            group_ids=await self._approver_groups.group_ids_for(caller, caller_roles),
        ):
            return
        raise ForbiddenError(
            "Only the execution initiator, a designated approver, or an admin "
            "can access this workflow execution"
        )
