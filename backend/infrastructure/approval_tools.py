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

A request also carries the WorkflowTask the approval takes effect **from**. It
covers that task and every task downstream of it, up to the next approval (see
:mod:`infrastructure.approval_scope`), so a workflow can put the request in a
step of its own -- "Ask for a go-ahead", then "Launch instance" -- and have the
decision reach the steps that follow without naming each one. Naming the asking
step is therefore the natural shape, not a mistake to reject.

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
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.approval_scope import active_approval_by_task, covered_task_ids
from infrastructure.approved_calls import declared_tools, validate_declaration
from infrastructure.tool_mocks import resolve_mock
from infrastructure.workflow_task_tools import (
    _NO_SESSION,
    _notify,
    _resolve_scope,
    _user_id,
)
from models.approval import ApprovalCreate, ApprovalStatus, ApprovedCall
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

#: Upper bound on how many of a run's tasks one scope computation reads. Mirrors
#: ``infrastructure.mcp_policies._MAX_TASKS``, which caps the same kind of
#: whole-run scan on the enforcement side.
_MAX_TASKS = 1000

#: Stands in for the approval that does not exist yet while its coverage is
#: computed. Any id no real approval can hold works; it never leaves
#: :func:`_prospective_tool_bindings`.
_PROSPECTIVE = "<prospective>"


async def _prospective_tool_bindings(
    s: _Scope, workflow_task_id: str
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    """Return the MCP tools an approval on this task would end up governing.

    The declaration a request must carry is checked against this, so the check
    has to know the coverage *before* the approval row exists. Rather than
    inventing a second notion of coverage, this runs the same walk
    :func:`_stand_down_superseded_grants` runs afterwards
    (:func:`infrastructure.approval_scope.covered_task_ids`) over an
    ``active_approval_by_task`` mapping with the named task pointed at a
    placeholder.

    Overriding the mapping rather than synthesizing an ``Approval`` row is what
    keeps this honest: a fresh ``pending`` request outranks whatever gated the
    task before it (:func:`infrastructure.approval_scope._outranks` prefers a
    pending approval, then the newer one), so the placeholder wins that task
    exactly as the real row will, and the tasks downstream follow from there.

    The pairs come back split by what the covered bindings ask for. A pair is
    exempt only when **every** covered binding of it clears
    ``requires_input_approval``: where one step wants the arguments approved and
    another does not, the stricter step decides, since the approval is a single
    decision covering both.

    Args:
        s: The current tool call's resolved run and repositories.
        workflow_task_id: The task the approval would take effect from.

    Returns:
        ``(constrained, exempt)`` -- the ``(mcp_server_id, tool_name)`` pairs the
        declaration must name, and the ones it must leave out because the
        workflow's design exempted them from input approval.
    """
    tasks = await s.task_repo.list(
        limit=_MAX_TASKS, offset=0, workflow_execution_id=s.execution_id
    )
    approvals = await s.approval_repo.list_for_execution(s.execution_id)
    active = active_approval_by_task(approvals) | {workflow_task_id: _PROSPECTIVE}
    covered = covered_task_ids(tasks, active, _PROSPECTIVE)
    requires: dict[tuple[str, str], bool] = {}
    for task in tasks:
        if task.id not in covered:
            continue
        for binding in task.tool_bindings:
            key = (binding.mcp_server_id, binding.tool_name)
            requires[key] = requires.get(key, False) or binding.requires_input_approval
    return (
        frozenset(pair for pair, needed in requires.items() if needed),
        frozenset(pair for pair, needed in requires.items() if not needed),
    )


def _render_tools(pairs: Collection[tuple[str, str]]) -> str:
    """Render ``(server, tool)`` pairs the way an error message names them.

    Args:
        pairs: The pairs to render.

    Returns:
        The pairs as a list of objects, sorted for a stable message.
    """
    return str([{"mcp_server_id": s, "tool_name": n} for s, n in sorted(pairs)])


def _declaration_mismatch_error(
    missing: Collection[tuple[str, str]],
    extra: Collection[tuple[str, str]],
    exempt: Collection[tuple[str, str]],
) -> str:
    """Explain a declaration that does not line up with the covered tools.

    An extra that is exempt gets its own clause. It is the one mistake the agent
    cannot diagnose from the tool list alone -- the tool *is* bound to a covered
    task, so "no task this approval covers is bound to it" would read as simply
    wrong -- and it is the mistake this exemption invites.

    Args:
        missing: Bound tools requiring input approval that the declaration fails
            to cover.
        extra: Declared tools that should not have been declared.
        exempt: Covered tools the workflow's design exempted from input
            approval, used to tell the two kinds of extra apart.

    Returns:
        The error message the agent is handed.
    """
    exempt_set = set(exempt)
    parts: list[str] = []
    if missing:
        parts.append(
            "it does not declare "
            + _render_tools(missing)
            + ", which the tasks this approval covers are bound to"
        )
    declared_exempt = [pair for pair in extra if pair in exempt_set]
    unbound = [pair for pair in extra if pair not in exempt_set]
    if declared_exempt:
        parts.append(
            "it declares "
            + _render_tools(declared_exempt)
            + ", which this workflow's design exempted from input approval -- "
            "leave those out and they are recorded as authorized with any "
            "arguments"
        )
    if unbound:
        parts.append(
            "it declares "
            + _render_tools(unbound)
            + ", which no task this approval covers is bound to"
        )
    return (
        "approved_calls must name exactly the MCP tools that are bound to the "
        "tasks this approval covers and require input approval, so the approver "
        "decides on every call it authorizes and on nothing that cannot happen: "
        + "; and ".join(parts)
        + ". Use list_workflow_tasks to see what those tasks bind, and which of "
        "their bindings have requires_input_approval set to false."
    )


async def _stand_down_superseded_grants(
    s: _Scope, approval_id: str, user_id: str
) -> None:
    """Revoke the grants held by the tasks a new approval has just taken over.

    A task can already be ``in_progress`` -- and therefore already holding a
    certificate, its run initiator's or an outer approval's -- when the agent
    decides a human has to weigh in. Every task the new approval now governs has
    to stand its old grant down, or the audit trail would show two live
    authorities for one task.

    Best-effort. The approval row has already committed by the time this runs,
    so raising here would report a failure for a write that succeeded. Nothing
    about the gate depends on it either: ``TaskCertificatePolicy`` re-derives the
    governing approval on every call and refuses any certificate that does not
    match it, stamped or not.

    The import is deferred to call time for the same reason the ones in
    :func:`_repos` are -- reaching into ``services`` at module import time closes
    a cycle back through ``infrastructure.agent``.

    Args:
        s: The current tool call's resolved run and repositories.
        approval_id: The approval that was just created.
        user_id: The acting user, recorded as ``updated_by``.
    """
    from services.mcp_tool_certificate import build_mcp_tool_certificate_service

    try:
        tasks = await s.task_repo.list(
            limit=_MAX_TASKS, offset=0, workflow_execution_id=s.execution_id
        )
        approvals = await s.approval_repo.list_for_execution(s.execution_id)
        covered = covered_task_ids(
            tasks, active_approval_by_task(approvals), approval_id
        )
        certificates = build_mcp_tool_certificate_service(s.db, tenant_id=s.tenant_id)
        await certificates.supersede_grants_for(sorted(covered), user_id=user_id)
    except Exception:
        logger.exception(
            "failed to stand down the tool grants covered by approval %s",
            approval_id,
        )


async def request_approval(
    title: str,
    tool_context: ToolContext,
    workflow_task_id: str,
    approved_calls: list[dict[str, Any]] | None = None,
    approver: str | None = None,
    approver_group_id: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a pending approval request and notify the approver(s).

    Call this before performing an action that needs a human go-ahead. It records
    a ``pending`` Approval for the current workflow execution and creates
    ``approval_request`` notifications so only the people who can decide are
    alerted. After it returns, explain the request to the user and call the
    client-side ``render_approval`` frontend tool with the returned
    ``approval_id`` to show approve/reject controls. Do NOT proceed with the
    action until the decision is ``approved``.

    ``workflow_task_id`` names **the task the approval takes effect from**. The
    approval covers that task and every task downstream of it, up to the next
    approval -- so if the workflow has a step whose whole job is to ask for the
    go-ahead, name that step and the decision will reach the steps that follow
    it. Until the decision is ``approved``, none of the covered tasks may call
    any of their bound MCP tools. Use ``list_workflow_tasks`` to find the id.

    ``approved_calls`` declares **exactly which MCP tool calls this approval
    authorizes**, argument by argument. The approver is shown this declaration
    and decides on it, and every later call is matched against it: a call naming
    an argument the declaration does not mention, omitting one it requires, or
    passing a value outside the declared bounds is **refused by the server**. So
    declare the calls you actually intend to make, then make exactly those.

    One entry per (server, tool) pair, and the declaration must name **every**
    tool bound to the tasks this approval covers **that requires input
    approval**, and no others. Each argument you will send maps to an object
    holding **exactly one** operator:

    * ``{"eq": <value>}`` -- must equal this value.
    * ``{"in": [<v>, ...]}`` -- must be one of these values.
    * ``{"lte": <number>}`` / ``{"gte": <number>}`` -- numeric bound, inclusive.
    * ``{"matches": "<regex>"}`` -- string matching this regular expression,
      unanchored, so write ``^`` and ``$`` yourself when you mean them.

    Add ``"optional": true`` beside the operator for an argument you may omit.
    The operator is always written out, never a bare value, so a literal that is
    itself an object or a list is never ambiguous. For example::

        [{"mcp_server_id": "<id>", "tool_name": "run_instances",
          "arguments": {"region": {"eq": "ap-northeast-1"},
                        "instance_type": {"in": ["t3.micro", "t3.small"]},
                        "count": {"lte": 2},
                        "name": {"matches": "^dev-"}}}]

    Call ``list_mcp_tools`` first to read each tool's input schema, and declare
    the narrowest values that still let the work succeed: a wider declaration is
    a wider grant, and a human is reading it.

    A bound tool whose ``requires_input_approval`` is false -- the workflow's
    design saying it only reads, so its arguments need nobody's agreement -- is
    the exception: **leave it out of the declaration**. Declaring one is
    refused. It is still covered by the approval and still cannot be called
    until the decision is ``approved``; it is simply recorded as authorized with
    any arguments, and shown to the approver that way. ``list_workflow_tasks``
    reports the flag on each binding.

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
        workflow_task_id: Id of the WorkflowTask the approval takes effect from;
            must belong to the current session. Required.
        approved_calls: The MCP tool calls this approval authorizes, each
            ``{"mcp_server_id": ..., "tool_name": ..., "arguments": {<name>:
            {<operator>: <value>}}}``. Required whenever any task this approval
            covers binds an MCP tool requiring input approval; omit it when none
            does. Never name a tool the design exempted, and never set
            ``unconstrained_arguments`` yourself.
        approver: Id of the single user the request is addressed to. Mutually
            exclusive with ``approver_group_id``; it must match an existing,
            enabled user holding the ``approver`` role.
        approver_group_id: Id of the user group the request is addressed to.
            Mutually exclusive with ``approver``; the group must have at least
            one member who can approve.
        description: Optional longer explanation of the request.

    Returns:
        On success ``{"approval_id": <id>, "status": "pending"}``. On failure
        ``{"error": <message>}`` (no destination or both, unresolved session,
        unknown task, unknown or ineligible approver or group, a declaration
        that is malformed, sets ``unconstrained_arguments``, or does not name
        exactly the tools the covered tasks bind that require input approval, or
        a persistence error). When
        the current run mocks this tool the destination, the task and the
        declaration are still
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
            task = await s.task_repo.get(workflow_task_id)
            if task is None or task.workflow_execution_id != s.execution_id:
                return {
                    "error": f"WorkflowTask {workflow_task_id!r} "
                    "not found in the current session"
                }
            try:
                declaration = [ApprovedCall(**entry) for entry in approved_calls or []]
            except (TypeError, ValidationError) as exc:
                return {
                    "error": "each entry of approved_calls must be "
                    '{"mcp_server_id": ..., "tool_name": ..., "arguments": '
                    "{<name>: {<operator>: <value>}}}: " + str(exc)
                }
            if any(call.unconstrained_arguments for call in declaration):
                return {
                    "error": "approved_calls entries may not set "
                    "unconstrained_arguments: which tools may be called with "
                    "any arguments is decided by the workflow's design, not by "
                    "this request. Leave those tools out of the declaration "
                    "entirely and they are recorded that way for you."
                }
            problems = validate_declaration(declaration)
            if problems:
                return {"error": "approved_calls is malformed: " + "; ".join(problems)}
            bound, exempt = await _prospective_tool_bindings(s, workflow_task_id)
            declared = declared_tools(declaration)
            if declared != bound:
                return {
                    "error": _declaration_mismatch_error(
                        bound - declared, declared - bound, exempt
                    )
                }
            # Recorded rather than resolved from the bindings at call time, so
            # the approver reads one list naming every tool the decision
            # authorizes and the gate matches against that same list.
            declaration += [
                ApprovedCall(
                    mcp_server_id=server_id,
                    tool_name=tool_name,
                    unconstrained_arguments=True,
                )
                for server_id, tool_name in sorted(exempt)
            ]
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
                approved_calls=declaration,
            )
            acting_user_id = _user_id(tool_context)
            try:
                approval = await s.approval_repo.create(data, user_id=acting_user_id)
            except ForeignKeyViolationError as exc:
                return {"error": str(exc)}
            # Capture the result before the stand-down and _notify commit again,
            # which would expire these attributes and trigger a lazy reload
            # outside the greenlet context.
            result = {"approval_id": approval.id, "status": approval.status.value}
            await _stand_down_superseded_grants(
                s, str(result["approval_id"]), acting_user_id
            )
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
