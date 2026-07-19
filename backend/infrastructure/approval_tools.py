"""ADK agent tools for requesting human approval during a workflow session.

These callables are attached to the skill-driven workflow agent (see
:func:`infrastructure.agent.create_agent`) so it can pause for a human decision
before performing a sensitive action. The agent calls :func:`request_approval`
to create a ``pending`` :class:`~models.approval.Approval` and notify the
designated approver, then invokes the client-side ``render_approval`` frontend
tool to show approve/reject controls. Only that approver can resolve the request:
their decision is written back to the approval record directly from the frontend
(``PATCH /approvals/{id}``); the agent learns the outcome from that tool's result
and can re-check it with :func:`get_approval`.

Like the WorkflowTask tools, these run *during* the AG-UI SSE stream outside
FastAPI's request scope, so each call opens its own ``AsyncSession`` on the
module-level engine and resolves the current WorkflowSession from the ADK
session id. They reuse the WorkflowTask tools' session-resolution, audit-user,
and notification helpers. Every tool returns plain JSON-serializable values,
mapping errors to an ``{"error": ...}`` payload instead of raising.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.workflow_task_tools import (
    _NO_SESSION,
    _notify,
    _resolve_scope,
    _user_id,
)
from models.approval import ApprovalCreate
from models.notification import NotificationType
from models.user import Role, User, has_role
from repositories import (
    ApprovalRepository,
    NotificationRepository,
    SqlApprovalRepository,
    SqlMCPServerRepository,
    SqlNotificationRepository,
    SqlUserRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    UserRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import ForeignKeyViolationError
from repositories.query import FilterSpec
from repositories.tenant_bootstrap import NoTenantSessionError

logger = logging.getLogger(__name__)


@dataclass
class _Scope:
    """Per-tool-call resolved WorkflowSession id, tenant id, and scoped repos."""

    ws_id: str
    tenant_id: str
    ws_repo: WorkflowSessionRepository
    approval_repo: ApprovalRepository
    task_repo: WorkflowTaskRepository
    notif_repo: NotificationRepository
    user_repo: UserRepository


@asynccontextmanager
async def _repos(tool_context: ToolContext) -> AsyncIterator[_Scope]:
    """Open a database session and yield the resolved scope and its repositories.

    Opens a fresh ``AsyncSession`` on the module-level engine (referenced through
    the ``database`` module so tests can monkeypatch ``database.engine``),
    resolves the current run's WorkflowSession id and tenant id, and wires the
    WorkflowSession, Approval, WorkflowTask, and Notification repositories to
    it, all scoped to the resolved tenant. The User repository is not tenant
    scoped -- ``User`` is not a ``TenantScoped`` entity.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Yields:
        The resolved :class:`_Scope`.

    Raises:
        NoTenantSessionError: If no WorkflowSession is bound to the current run.
    """
    async with AsyncSession(database.engine) as db:
        ws_id, tenant_id = await _resolve_scope(tool_context, db)
        ws_repo = SqlWorkflowSessionRepository(db, tenant_id=tenant_id)
        yield _Scope(
            ws_id=ws_id,
            tenant_id=tenant_id,
            ws_repo=ws_repo,
            approval_repo=SqlApprovalRepository(db, ws_repo, tenant_id=tenant_id),
            task_repo=SqlWorkflowTaskRepository(
                db,
                ws_repo,
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            ),
            notif_repo=SqlNotificationRepository(db, tenant_id=tenant_id),
            user_repo=SqlUserRepository(db),
        )


def _is_eligible_approver(user: User | None, *, tenant_id: str) -> bool:
    """Return whether a user may be designated as an approval's approver.

    Eligible approvers belong to the given tenant, are enabled, not
    soft-deleted, and hold the ``approver`` role (``super_admin`` also
    qualifies for the role check, since it bypasses every role check, but
    still must belong to the tenant -- there is no cross-tenant bypass). Since
    a ``super_admin`` can never carry a ``tenant_id`` (see the
    ``ck_users_super_admin_no_tenant`` constraint on :class:`~models.user.User`),
    this means a super admin is never eligible as approver for a
    tenant-scoped session -- there is no platform-scoped exception here.

    Args:
        user: The candidate user, or ``None`` when the lookup found nobody.
        tenant_id: Tenant the approver must belong to (the current run's
            resolved tenant).

    Returns:
        ``True`` if the user exists and may receive approval requests.
    """
    return (
        user is not None
        and user.enabled
        and user.deleted_at is None
        and user.tenant_id == tenant_id
        and has_role(user, Role.approver)
    )


async def request_approval(
    title: str,
    tool_context: ToolContext,
    approver: str,
    description: str | None = None,
    workflow_task_id: str | None = None,
) -> dict[str, Any]:
    """Create a pending approval request and notify the designated approver.

    Call this before performing an action that needs a human go-ahead. It records
    a ``pending`` Approval for the current workflow session and creates an
    ``approval_request`` notification addressed to ``approver`` so only they are
    alerted. After it returns, explain the request to the user and call the
    client-side ``render_approval`` frontend tool with the returned ``approval_id``
    to show approve/reject controls; only the designated approver can resolve the
    request, and their decision comes back as that tool's result. Do NOT proceed
    with the action until the decision is ``approved``.

    Args:
        title: Short headline describing what needs approval (required).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        approver: Id of the user the request is addressed to (required). Only this
            user receives the notification and may resolve the request; it must
            match an existing, enabled user holding the ``approver`` role. Use
            :func:`list_users` to discover eligible ids.
        description: Optional longer explanation of the request.
        workflow_task_id: Optional id of the WorkflowTask this approval concerns;
            must belong to the current session.

    Returns:
        On success ``{"approval_id": <id>, "status": "pending"}``. On failure
        ``{"error": <message>}`` (missing approver, unresolved session, unknown
        task, unknown approver, or a persistence error).
    """
    if not approver:
        return {"error": "approver is required"}
    try:
        async with _repos(tool_context) as s:
            if workflow_task_id is not None:
                task = await s.task_repo.get(workflow_task_id)
                if task is None or task.workflow_session_id != s.ws_id:
                    return {
                        "error": f"WorkflowTask {workflow_task_id!r} "
                        "not found in the current session"
                    }
            if not _is_eligible_approver(
                await s.user_repo.get(approver), tenant_id=s.tenant_id
            ):
                return {
                    "error": f"User {approver!r} cannot be designated as an approver: "
                    "the user must exist, be enabled, and hold the approver role. "
                    "Use list_users to discover eligible approvers."
                }
            data = ApprovalCreate(
                workflow_session_id=s.ws_id,
                title=title,
                description=description,
                workflow_task_id=workflow_task_id,
                approver=approver,
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
            await _notify(
                s.ws_repo,
                s.notif_repo,
                s.ws_id,
                NotificationType.approval_request,
                title,
                body=description,
                recipient=approver,
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
            return {
                "users": [
                    _user_to_dict(u)
                    for u in users
                    if _is_eligible_approver(u, tenant_id=s.tenant_id)
                ]
            }
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def get_approval(approval_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Fetch the current state of an approval in the current session.

    Use this to re-check a decision (for example after calling ``render_approval``)
    before continuing.

    Args:
        approval_id: Id of the approval to fetch.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        On success ``{"approval_id", "title", "status", "response", "approver",
        "workflow_task_id"}``. On failure ``{"error": <message>}`` if the session
        cannot be resolved or the approval does not belong to it.
    """
    try:
        async with _repos(tool_context) as s:
            approval = await s.approval_repo.get(approval_id)
            if approval is None or approval.workflow_session_id != s.ws_id:
                return {
                    "error": f"Approval {approval_id!r} not found in the current session"
                }
            return {
                "approval_id": approval.id,
                "title": approval.title,
                "status": approval.status.value,
                "response": approval.response,
                "approver": approval.approver,
                "workflow_task_id": approval.workflow_task_id,
            }
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
