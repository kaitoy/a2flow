"""ADK agent tools for requesting human approval during a workflow execution.

These callables are attached to the skill-driven workflow agent (see
:func:`infrastructure.agent.create_agent`) so it can pause for a human decision
before performing a sensitive action. The agent calls :func:`request_approval`
to create a ``pending`` :class:`~models.approval.Approval` and notify whoever
can decide it, then invokes the client-side ``render_approval`` frontend tool to
show approve/reject controls. The decision is written back to the approval
record directly from the frontend (``PATCH /approvals/{id}``); the agent learns
the outcome from that tool's result and can re-check it with
:func:`get_approval`.

A request carries exactly one destination, and each has a discovery tool:
:func:`list_users` finds individuals eligible as ``approver``, and
:func:`list_user_groups` finds teams eligible as ``approver_group_id``. Only
the destination can resolve the request -- for a group that means any member
holding the ``approver`` role, whose single decision settles it. Both discovery
tools and the eligibility check share :func:`_is_eligible_approver`, so who a
request may be *addressed* to and who may *act* on it never drift apart.

A draft run may mock :func:`request_approval` (see
:mod:`infrastructure.tool_mocks`). The destination is still validated -- a run
that names an ineligible approver should fail the same way mocked or not -- but
no Approval is recorded, nobody is notified, and the mock's per-call response is
returned instead, letting a test run drive the approval path to a decision (or
through several successive ones) without a human.

Like the WorkflowTask tools, these run *during* the AG-UI SSE stream outside
FastAPI's request scope, so each call opens its own ``AsyncSession`` on the
module-level engine and resolves the current WorkflowExecution from the ADK
session id. They reuse the WorkflowTask tools' session-resolution, audit-user,
and notification helpers. Every tool returns plain JSON-serializable values,
mapping errors to an ``{"error": ...}`` payload instead of raising.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.tool_mocks import resolve_mock
from infrastructure.workflow_task_tools import (
    _NO_SESSION,
    _notify,
    _resolve_scope,
    _user_id,
)
from models.approval import ApprovalCreate, ApprovalStatus
from models.mcp_tool_mock import (
    REQUEST_APPROVAL_TOOL,
    MockResponse,
    MockResponseKind,
)
from models.notification import NotificationType
from models.user import Role, User, has_any_role
from repositories import (
    ApprovalRepository,
    EffectiveRoleRepository,
    SqlApprovalRepository,
    SqlEffectiveRoleRepository,
    SqlMCPServerRepository,
    SqlUserGroupRepository,
    SqlUserRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
    UserGroupRepository,
    UserRepository,
    WorkflowExecutionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import ForeignKeyViolationError
from repositories.query import FilterSpec
from repositories.tenant_bootstrap import NoTenantSessionError

if TYPE_CHECKING:
    # Type-only for the same reason as in ``infrastructure.workflow_task_tools``:
    # importing a ``services`` submodule at runtime closes an import cycle back
    # through ``infrastructure.agent``. The runtime import lives in
    # :func:`_repos`.
    from services.notification_dispatch import NotificationDispatcher

logger = logging.getLogger(__name__)


@dataclass
class _Scope:
    """Per-tool-call resolved WorkflowExecution id, tenant id, and scoped repos."""

    # Note: ``user_repo`` and ``effective_role_repo`` are deliberately not
    # tenant scoped -- neither ``User`` nor a membership row is a
    # ``TenantScoped`` entity. Every caller still checks ``user.tenant_id``
    # itself, via ``_is_eligible_approver``.

    execution_id: str
    tenant_id: str
    #: The open session the repositories below share, exposed so
    #: :func:`infrastructure.tool_mocks.resolve_mock` can read and advance the
    #: run's mock state on the same transaction.
    db: AsyncSession
    execution_repo: WorkflowExecutionRepository
    approval_repo: ApprovalRepository
    task_repo: WorkflowTaskRepository
    # Quoted for the same reason as ``_Scope.notifications`` in
    # ``workflow_task_tools``: the name only exists under TYPE_CHECKING.
    notifications: "NotificationDispatcher"
    user_repo: UserRepository
    effective_role_repo: EffectiveRoleRepository
    group_repo: UserGroupRepository


@asynccontextmanager
async def _repos(tool_context: ToolContext) -> AsyncIterator[_Scope]:
    """Open a database session and yield the resolved scope and its repositories.

    Opens a fresh ``AsyncSession`` on the module-level engine (referenced through
    the ``database`` module so tests can monkeypatch ``database.engine``),
    resolves the current run's WorkflowExecution id and tenant id, and wires the
    WorkflowExecution, Approval, and WorkflowTask repositories plus the
    notification dispatcher to it, all scoped to the resolved tenant. The User
    repository is not tenant scoped -- ``User`` is not a ``TenantScoped`` entity.

    The dispatcher's import is deferred to call time to avoid the ``services``
    import cycle described on the TYPE_CHECKING block above.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Yields:
        The resolved :class:`_Scope`.

    Raises:
        NoTenantSessionError: If no WorkflowExecution is bound to the current run.
    """
    from services.notification_dispatch import build_notification_dispatcher

    async with AsyncSession(database.engine) as db:
        execution_id, tenant_id = await _resolve_scope(tool_context, db)
        execution_repo = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
        user_repo = SqlUserRepository(db)
        group_repo = SqlUserGroupRepository(db, user_repo, tenant_id=tenant_id)
        yield _Scope(
            execution_id=execution_id,
            tenant_id=tenant_id,
            db=db,
            execution_repo=execution_repo,
            approval_repo=SqlApprovalRepository(
                db, execution_repo, group_repo, tenant_id=tenant_id
            ),
            task_repo=SqlWorkflowTaskRepository(
                db,
                execution_repo,
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            ),
            notifications=build_notification_dispatcher(db, tenant_id=tenant_id),
            user_repo=user_repo,
            effective_role_repo=SqlEffectiveRoleRepository(db),
            group_repo=group_repo,
        )


def _is_eligible_approver(
    user: User | None, *, tenant_id: str, effective_roles: Collection[str]
) -> bool:
    """Return whether a user may be designated as an approval's approver.

    Eligible approvers belong to the given tenant, are enabled, not
    soft-deleted, and hold the ``approver`` role (``super_admin`` also
    qualifies for the role check, since it bypasses every role check, but
    still must belong to the tenant -- there is no cross-tenant bypass). Since
    a ``super_admin`` can never carry a ``tenant_id`` (see the
    ``ck_users_super_admin_no_tenant`` constraint on :class:`~models.user.User`),
    this means a super admin is never eligible as approver for a
    tenant-scoped session -- there is no platform-scoped exception here.

    The role test runs against **effective** roles, so a user who holds
    ``approver`` only through a :class:`~models.user_group.UserGroup` is just
    as eligible as one granted it directly. The caller resolves them, batching
    the lookup where it has several candidates.

    Args:
        user: The candidate user, or ``None`` when the lookup found nobody.
        tenant_id: Tenant the approver must belong to (the current run's
            resolved tenant).
        effective_roles: The candidate's direct roles unioned with the roles of
            every group they belong to.

    Returns:
        ``True`` if the user exists and may receive approval requests.
    """
    return (
        user is not None
        and user.enabled
        and user.deleted_at is None
        and user.tenant_id == tenant_id
        and has_any_role(effective_roles, Role.approver)
    )


def _filter_eligible(
    users: Sequence[User],
    inherited: Mapping[str, frozenset[str]],
    *,
    tenant_id: str,
) -> list[User]:
    """Return the users of ``users`` who may be designated as an approver.

    Split out from :func:`_eligible_members` so the single-group and
    whole-tenant paths share one predicate without either re-querying: both
    resolve their users and inherited roles in bulk first, then filter here.

    Args:
        users: The candidate users, already fetched.
        inherited: Group-inherited roles keyed by user id, as returned by
            :meth:`repositories.effective_roles.EffectiveRoleRepository.group_roles_for_users`.
        tenant_id: Tenant the approvers must belong to.

    Returns:
        The subset of ``users`` that passes :func:`_is_eligible_approver`.
    """
    return [
        u
        for u in users
        if _is_eligible_approver(
            u,
            tenant_id=tenant_id,
            effective_roles=set(u.roles or []) | inherited.get(u.id, frozenset()),
        )
    ]


async def _eligible_members(s: _Scope, member_ids: Sequence[str]) -> list[User]:
    """Return the members of one group who may resolve its approvals.

    Two queries regardless of group size -- one for the users, one for every
    membership behind their inherited roles -- mirroring :func:`list_users`.

    Args:
        s: The resolved per-call scope.
        member_ids: Ids of the group's members.

    Returns:
        The eligible members, empty when the group has none.
    """
    if not member_ids:
        return []
    users = await s.user_repo.get_many(list(member_ids))
    inherited = await s.effective_role_repo.group_roles_for_users([u.id for u in users])
    return _filter_eligible(users, inherited, tenant_id=s.tenant_id)


#: Appended to every mocked approval result. The execution agent is cached per
#: skill revision, so its instruction cannot vary per run; the tool's own result
#: is what tells the model this decision is final and that the client-side
#: approval UI must not be shown for it.
_MOCK_NOTE = (
    "Mock run: no approval record was created and nobody was notified. "
    "Do NOT call render_approval and do NOT poll get_approval; "
    "treat this status as final."
)


def _mocked_approval(response: MockResponse) -> dict[str, Any]:
    """Build the tool result for a mocked approval request.

    A ``structured`` mock supplies the payload directly, which is what makes a
    scenario expressible -- ``{"status": "approved"}`` for the first request and
    ``{"status": "rejected"}`` for the second. A ``text`` mock is read as the
    status alone. Either way an ``approval_id`` is synthesized when the mock does
    not name one, so the model has something to refer to; it deliberately does
    not exist in ``approvals``, since nothing was recorded.

    Args:
        response: The mocked response selected for this call.

    Returns:
        The dict the tool returns to the model.
    """
    if response.kind is MockResponseKind.error:
        return {"error": str(response.value)}
    payload: dict[str, Any] = (
        dict(response.value)
        if response.kind is MockResponseKind.structured
        else {"status": str(response.value)}
    )
    payload.setdefault("approval_id", f"mock-{uuid.uuid4()}")
    payload.setdefault("status", ApprovalStatus.approved.value)
    payload["mocked"] = True
    payload["note"] = _MOCK_NOTE
    return payload


#: Upper bound on the notifications one group-addressed request fans out to.
#: A group is normally a handful of people; the cap stops one tool call from
#: turning a pathologically large group into that many separate commits.
_MAX_NOTIFICATION_FANOUT = 100


async def request_approval(
    title: str,
    tool_context: ToolContext,
    approver: str | None = None,
    approver_group_id: str | None = None,
    description: str | None = None,
    workflow_task_id: str | None = None,
) -> dict[str, Any]:
    """Create a pending approval request and notify the approver(s).

    Call this before performing an action that needs a human go-ahead. It records
    a ``pending`` Approval for the current workflow execution and creates
    ``approval_request`` notifications so only the people who can decide are
    alerted. After it returns, explain the request to the user and call the
    client-side ``render_approval`` frontend tool with the returned
    ``approval_id`` to show approve/reject controls. Do NOT proceed with the
    action until the decision is ``approved``.

    Address the request to **exactly one** destination:

    * ``approver`` -- one specific person. Only they are notified and only they
      can resolve it. Discover ids with :func:`list_users`.
    * ``approver_group_id`` -- a team. Every eligible member is notified, and
      the **first** decision from any of them settles the request, so it is not
      blocked on one person's availability. Discover ids with
      :func:`list_user_groups`.

    Prefer a group whenever any member of a team may decide; name a single user
    when the Skill calls for a specific person.

    Args:
        title: Short headline describing what needs approval (required).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        approver: Id of the single user the request is addressed to. Mutually
            exclusive with ``approver_group_id``; it must match an existing,
            enabled user holding the ``approver`` role.
        approver_group_id: Id of the user group the request is addressed to.
            Mutually exclusive with ``approver``; the group must have at least
            one member who can approve.
        description: Optional longer explanation of the request.
        workflow_task_id: Optional id of the WorkflowTask this approval concerns;
            must belong to the current session.

    Returns:
        On success ``{"approval_id": <id>, "status": "pending"}``. On failure
        ``{"error": <message>}`` (no destination or both, unresolved session,
        unknown task, unknown or ineligible approver or group, or a persistence
        error). When the current run mocks this tool the destination is still
        validated but nothing is recorded or notified, and the mock's response
        comes back with ``"mocked": true`` and a ``note`` saying the status is
        final -- typically already ``approved``, so the run continues unattended.
    """
    if (approver is None or not approver) == (
        approver_group_id is None or not approver_group_id
    ):
        return {
            "error": "exactly one of approver or approver_group_id is required: "
            "use list_users to address one person, or list_user_groups to "
            "address a team"
        }
    try:
        async with _repos(tool_context) as s:
            if workflow_task_id is not None:
                task = await s.task_repo.get(workflow_task_id)
                if task is None or task.workflow_execution_id != s.execution_id:
                    return {
                        "error": f"WorkflowTask {workflow_task_id!r} "
                        "not found in the current session"
                    }
            if approver:
                candidate = await s.user_repo.get(approver)
                if not _is_eligible_approver(
                    candidate,
                    tenant_id=s.tenant_id,
                    effective_roles=(
                        frozenset()
                        if candidate is None
                        else await s.effective_role_repo.effective_roles_for_user(
                            candidate.id, candidate.roles or []
                        )
                    ),
                ):
                    return {
                        "error": f"User {approver!r} cannot be designated as an "
                        "approver: the user must exist, be enabled, and hold the "
                        "approver role. Use list_users to discover eligible "
                        "approvers."
                    }
                recipients = [approver]
            else:
                assert approver_group_id is not None
                group = await s.group_repo.get(approver_group_id)
                if group is None:
                    return {
                        "error": f"User group {approver_group_id!r} not found in "
                        "the current tenant. Use list_user_groups to discover "
                        "eligible groups."
                    }
                members = await _eligible_members(s, group.member_ids)
                # A group nobody can approve for would produce a request that
                # wedges the run forever, so it is rejected up front rather
                # than created and then discovered to be undecidable.
                if not members:
                    return {
                        "error": f"User group {group.name!r} has no member who can "
                        "approve: at least one member must be enabled and hold the "
                        "approver role. Use list_user_groups to discover eligible "
                        "groups."
                    }
                recipients = [u.id for u in members]
            # Checked above, before this branch: a mock is meant to skip the
            # side effects, not the validation. A run that names an ineligible
            # approver should fail the same way mocked or not.
            mocked = await resolve_mock(
                s.db,
                s.execution_id,
                tenant_id=s.tenant_id,
                server_id=None,
                tool_name=REQUEST_APPROVAL_TOOL,
            )
            if mocked is not None:
                return _mocked_approval(mocked)
            data = ApprovalCreate(
                workflow_execution_id=s.execution_id,
                title=title,
                description=description,
                workflow_task_id=workflow_task_id,
                approver=approver or None,
                approver_group_id=approver_group_id or None,
            )
            try:
                approval = await s.approval_repo.create(
                    data, user_id=_user_id(tool_context)
                )
            except ForeignKeyViolationError as exc:
                return {"error": str(exc)}
            # Capture the result before _notify commits again, which would expire
            # these attributes and trigger a lazy reload outside the greenlet context.
            result = {"approval_id": approval.id, "status": approval.status.value}
            if len(recipients) > _MAX_NOTIFICATION_FANOUT:
                logger.warning(
                    "approval %s addressed to group %s has %d eligible members; "
                    "notifying only the first %d",
                    result["approval_id"],
                    approver_group_id,
                    len(recipients),
                    _MAX_NOTIFICATION_FANOUT,
                )
                recipients = recipients[:_MAX_NOTIFICATION_FANOUT]
            for recipient in recipients:
                await _notify(
                    s.execution_repo,
                    s.notifications,
                    s.execution_id,
                    NotificationType.approval_request,
                    title,
                    body=description,
                    recipient=recipient,
                )
            return result
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


def _user_to_dict(user: User) -> dict[str, Any]:
    """Convert a User into the plain dict the approver-selection tool returns."""
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
    }


async def list_users(tool_context: ToolContext) -> dict[str, Any]:
    """List the users eligible to be addressed as an approval's ``approver``.

    Call this before :func:`request_approval` to discover valid ``approver`` ids:
    pick the intended person from the returned list and pass their ``id`` as the
    ``approver`` argument. Only enabled users holding the ``approver`` role (or
    ``super_admin``) *and* belonging to the current run's tenant are returned;
    soft-deleted accounts, other tenants' users, platform-scoped users, and the
    internal system user are excluded.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"users": [{"id", "username", "first_name", "last_name",
        "email"}, ...]}`` ordered by creation time (newest first). On failure
        ``{"error": <message>}`` if the session cannot be resolved to a tenant.
    """
    try:
        async with _repos(tool_context) as s:
            users = await s.user_repo.list(
                limit=1000,
                offset=0,
                filters=[FilterSpec(field="tenantId", op="eq", value=s.tenant_id)],
            )
            # One query for the whole page's group memberships, not one per
            # candidate.
            inherited = await s.effective_role_repo.group_roles_for_users(
                [u.id for u in users]
            )
            return {
                "users": [
                    _user_to_dict(u)
                    for u in users
                    if _is_eligible_approver(
                        u,
                        tenant_id=s.tenant_id,
                        effective_roles=set(u.roles or [])
                        | inherited.get(u.id, frozenset()),
                    )
                ]
            }
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def list_user_groups(tool_context: ToolContext) -> dict[str, Any]:
    """List the user groups an approval request can be addressed to.

    Call this before :func:`request_approval` when a *team* rather than one
    named person should decide, and pass the chosen group's ``id`` as the
    ``approver_group_id`` argument. Every eligible member is then notified and
    the first decision from any of them completes the request, so it is not
    blocked on one person's availability.

    Only groups of the current run's tenant that have at least one member able
    to approve are returned -- a group with none could never resolve the
    request. ``eligible_approver_count`` says how many members that is, which
    is worth mentioning to the user when it is 1.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"groups": [{"id", "name", "description",
        "eligible_approver_count"}, ...]}``. On failure ``{"error": <message>}``
        if the session cannot be resolved to a tenant.
    """
    try:
        async with _repos(tool_context) as s:
            groups = await s.group_repo.list(limit=1000, offset=0)
            # Resolve every group's members with one pair of queries for the
            # whole page rather than one pair per group.
            all_member_ids = {mid for g in groups for mid in g.member_ids}
            if not all_member_ids:
                return {"groups": []}
            users = await s.user_repo.get_many(sorted(all_member_ids))
            inherited = await s.effective_role_repo.group_roles_for_users(
                [u.id for u in users]
            )
            eligible_ids = {
                u.id for u in _filter_eligible(users, inherited, tenant_id=s.tenant_id)
            }
            out = []
            for group in groups:
                count = sum(1 for mid in group.member_ids if mid in eligible_ids)
                if count:
                    out.append(
                        {
                            "id": group.id,
                            "name": group.name,
                            "description": group.description,
                            "eligible_approver_count": count,
                        }
                    )
            out.sort(key=lambda g: str(g["name"]))
            return {"groups": out}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def get_approval(approval_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Fetch the current state of an approval in the current session.

    Use this to re-check a decision (for example after calling ``render_approval``)
    before continuing. ``status`` is one of "pending" (still waiting), "approved"
    (go ahead), "rejected" (stop; do not retry), or "returned" (the approver
    wants the work revised and re-submitted — address their ``response`` comment
    and request approval again rather than abandoning the task).

    Args:
        approval_id: Id of the approval to fetch.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"approval_id", "title", "status", "response", "approver",
        "approver_group_id", "decided_by", "workflow_task_id"}``. Exactly one of
        ``approver`` / ``approver_group_id`` is set; ``decided_by`` names the
        user who actually decided (``None`` while pending), which for a
        group-addressed request is the only record of who acted. On failure
        ``{"error": <message>}`` if the session cannot be resolved or the
        approval does not belong to it.
    """
    try:
        async with _repos(tool_context) as s:
            approval = await s.approval_repo.get(approval_id)
            if approval is None or approval.workflow_execution_id != s.execution_id:
                return {
                    "error": f"Approval {approval_id!r} not found in the current session"
                }
            return {
                "approval_id": approval.id,
                "title": approval.title,
                "status": approval.status.value,
                "response": approval.response,
                "approver": approval.approver,
                "approver_group_id": approval.approver_group_id,
                "decided_by": approval.decided_by,
                "workflow_task_id": approval.workflow_task_id,
            }
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
