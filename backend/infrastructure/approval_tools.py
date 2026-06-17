"""ADK agent tools for requesting human approval during a workflow session.

These callables are attached to the skill-driven workflow agent (see
:func:`infrastructure.agent.create_agent`) so it can pause for a human decision
before performing a sensitive action. The agent calls :func:`request_approval`
to create a ``pending`` :class:`~models.approval.Approval` and notify the
session owner, then invokes the client-side ``render_approval`` frontend tool to
show approve/reject controls. The approver's decision is written back to the
approval record directly from the frontend (``PATCH /approvals/{id}``); the
agent learns the outcome from that tool's result and can re-check it with
:func:`get_approval`.

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
from typing import Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.workflow_task_tools import (
    _NO_SESSION,
    _notify,
    _resolve_ws_id,
    _user_id,
)
from models.approval import ApprovalCreate
from models.notification import NotificationType
from models.user import User
from repositories import (
    ApprovalRepository,
    NotificationRepository,
    SqlApprovalRepository,
    SqlMCPServerRepository,
    SqlNotificationRepository,
    SqlUserRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import ForeignKeyViolationError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _repos() -> AsyncIterator[
    tuple[
        WorkflowSessionRepository,
        ApprovalRepository,
        WorkflowTaskRepository,
        NotificationRepository,
    ]
]:
    """Open a database session and yield the repositories the approval tools need.

    Opens a fresh ``AsyncSession`` on the module-level engine (referenced through
    the ``database`` module so tests can monkeypatch ``database.engine``) and
    wires the WorkflowSession, Approval, WorkflowTask, and Notification
    repositories to it.

    Yields:
        A ``(workflow_session_repository, approval_repository,
        workflow_task_repository, notification_repository)`` tuple bound to the
        same session.
    """
    async with AsyncSession(database.engine) as db:
        ws_repo = SqlWorkflowSessionRepository(db)
        yield (
            ws_repo,
            SqlApprovalRepository(db, ws_repo),
            SqlWorkflowTaskRepository(db, ws_repo, SqlMCPServerRepository(db)),
            SqlNotificationRepository(db),
        )


async def request_approval(
    title: str,
    tool_context: ToolContext,
    description: str | None = None,
    workflow_task_id: str | None = None,
    approver: str | None = None,
) -> dict[str, Any]:
    """Create a pending approval request and notify the session owner.

    Call this before performing an action that needs the user's go-ahead. It
    records a ``pending`` Approval for the current workflow session and creates an
    ``approval_request`` notification so the user is alerted. After it returns,
    explain the request to the user and call the client-side ``render_approval``
    frontend tool with the returned ``approval_id`` to show approve/reject
    controls; the user's decision comes back as that tool's result. Do NOT
    proceed with the action until the decision is ``approved``.

    Args:
        title: Short headline describing what needs approval (required).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.
        description: Optional longer explanation of the request.
        workflow_task_id: Optional id of the WorkflowTask this approval concerns;
            must belong to the current session.
        approver: Optional id of the user the request is addressed to (its
            destination); must match an existing user. Use :func:`list_users` to
            discover valid ids.

    Returns:
        On success ``{"approval_id": <id>, "status": "pending"}``. On failure
        ``{"error": <message>}`` (unresolved session, unknown task, unknown
        approver, or a persistence error).
    """
    async with _repos() as (ws_repo, approval_repo, task_repo, notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        if workflow_task_id is not None:
            task = await task_repo.get(workflow_task_id)
            if task is None or task.workflow_session_id != ws_id:
                return {
                    "error": f"WorkflowTask {workflow_task_id!r} "
                    "not found in the current session"
                }
        data = ApprovalCreate(
            workflow_session_id=ws_id,
            title=title,
            description=description,
            workflow_task_id=workflow_task_id,
            approver=approver,
        )
        try:
            approval = await approval_repo.create(data, user_id=_user_id(tool_context))
        except ForeignKeyViolationError as exc:
            return {"error": str(exc)}
        # Capture the result before _notify commits again, which would expire
        # these attributes and trigger a lazy reload outside the greenlet context.
        result = {"approval_id": approval.id, "status": approval.status.value}
        await _notify(
            ws_repo,
            notif_repo,
            ws_id,
            NotificationType.approval_request,
            title,
            body=description,
        )
        return result


def _user_to_dict(user: User) -> dict[str, Any]:
    """Convert a User into the plain dict the approver-selection tool returns."""
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
    }


async def list_users() -> dict[str, Any]:
    """List the registered users who can be addressed as an approval's ``approver``.

    Call this before :func:`request_approval` to discover valid ``approver`` ids:
    pick the intended person from the returned list and pass their ``id`` as the
    ``approver`` argument. Soft-deleted accounts and the internal system user are
    excluded.

    Returns:
        ``{"users": [{"id", "username", "first_name", "last_name", "email"}, ...]}``
        ordered by creation time (newest first).
    """
    async with AsyncSession(database.engine) as db:
        user_repo = SqlUserRepository(db)
        users = await user_repo.list(limit=1000, offset=0)
        return {"users": [_user_to_dict(u) for u in users]}


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
    async with _repos() as (ws_repo, approval_repo, _task_repo, _notif_repo):
        ws_id = await _resolve_ws_id(tool_context, ws_repo)
        if ws_id is None:
            return {"error": _NO_SESSION}
        approval = await approval_repo.get(approval_id)
        if approval is None or approval.workflow_session_id != ws_id:
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
