"""Use case service for WorkflowTask resources.

Wraps the :class:`WorkflowTaskRepository` with the business rules the router
needs: raising :class:`NotFoundError` when a task is missing and authorizing
every operation against the task's parent workflow session — only the session
owner, a designated approver of the session, or a super admin may read or
modify a session's tasks. Changing a task's ``status`` is further restricted
when the task has a linked ``Approval`` (``Approval.workflow_task_id``): only
the session owner or that Approval's designated ``approver`` may do so — not
merely any approver of the session — mirroring ``ApprovalService.resolve``'s
no-bypass rule.
"""

from models.user import User
from models.workflow_task import (
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)
from repositories import (
    ApprovalRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import (
    ForbiddenError,
    ForeignKeyViolationError,
    NotFoundError,
)
from services.workflow_session_access import WorkflowSessionAccessPolicy


class WorkflowTaskService:
    """Application service orchestrating WorkflowTask operations."""

    def __init__(
        self,
        repo: WorkflowTaskRepository,
        ws_repo: WorkflowSessionRepository,
        access: WorkflowSessionAccessPolicy,
        approvals: ApprovalRepository,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTask persistence.
            ws_repo: Repository used to resolve a task's parent session for
                the access check.
            access: Policy restricting task operations to the session owner,
                the session's designated approvers, and super admins.
            approvals: Repository used to look up whether a task being updated
                has a linked Approval and, if so, its designated approver, to
                restrict ``status`` changes on such tasks.
        """
        self._repo = repo
        self._ws_repo = ws_repo
        self._access = access
        self._approvals = approvals

    async def _assert_session_access(self, ws_id: str, caller: User) -> None:
        """Authorize the caller against a task's parent workflow session.

        Args:
            ws_id: Identifier of the parent workflow session.
            caller: The authenticated user performing the task operation.

        Raises:
            NotFoundError: If the parent session does not exist (so a missing
                parent surfaces as 404 before any 403).
            ForbiddenError: If the caller is neither the session owner, a
                designated approver of the session, nor a super admin.
        """
        ws = await self._ws_repo.get(ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        await self._access.assert_access(ws_id, ws.user_id, caller)

    async def _assert_status_change_allowed(
        self, task: WorkflowTaskRead, caller: User
    ) -> None:
        """Restrict a ``status`` transition on a task with a linked Approval.

        Only applies when the task has a linked Approval with a non-null
        ``approver``; tasks without one keep the broader rule already enforced
        by :meth:`_assert_session_access`. No ``super_admin`` bypass, for
        consistency with ``ApprovalService.resolve``'s no-bypass rule — this
        check protects the same "only the addressee decides" invariant,
        reachable here via the task's ``status`` field instead of the
        Approval's own ``status`` field.

        Args:
            task: The task whose ``status`` is being changed.
            caller: The authenticated user performing the update.

        Raises:
            ForbiddenError: If the caller is neither the session owner nor the
                linked Approval's designated approver.
        """
        approval = await self._approvals.get_for_task(task.id)
        if approval is None or approval.approver is None:
            return
        if caller.id == approval.approver:
            return
        ws = await self._ws_repo.get(task.workflow_session_id)
        if ws is not None and caller.id == ws.user_id:
            return
        raise ForbiddenError(
            "Only the session owner or the linked approval's designated "
            "approver can change this task's status"
        )

    async def get(self, task_id: str, *, caller: User) -> WorkflowTaskRead:
        """Return the WorkflowTask with the given ID.

        Args:
            task_id: Identifier of the task to fetch.
            caller: The authenticated user requesting the task.

        Returns:
            The matching WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not access the task's session.
        """
        task = await self._repo.get(task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        await self._assert_session_access(task.workflow_session_id, caller)
        return task

    async def create(
        self, data: WorkflowTaskCreate, *, caller: User
    ) -> WorkflowTaskRead:
        """Create a new WorkflowTask.

        A missing parent session surfaces as a foreign-key violation (HTTP
        422), matching the pre-authorization behavior of the repository's own
        FK check, rather than the 404 used when the session appears in the
        URL path.

        Args:
            data: Fields for the new task, including its parent session.
            caller: The authenticated user creating the task.

        Returns:
            The created WorkflowTask.

        Raises:
            ForeignKeyViolationError: If the parent session does not exist.
            ForbiddenError: If the caller may not access the parent session.
        """
        ws = await self._ws_repo.get(data.workflow_session_id)
        if ws is None:
            raise ForeignKeyViolationError("WorkflowSession", data.workflow_session_id)
        await self._access.assert_access(data.workflow_session_id, ws.user_id, caller)
        return await self._repo.create(data, user_id=caller.id)

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, caller: User
    ) -> WorkflowTaskRead:
        """Apply a partial update to a WorkflowTask.

        Changing ``status`` on a task with a linked Approval is further
        restricted to the session owner or that Approval's designated
        approver, on top of the general session-access check — see
        :meth:`_assert_status_change_allowed`.

        Args:
            task_id: Identifier of the task to update.
            data: Fields to update.
            caller: The authenticated user performing the update.

        Returns:
            The updated WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not access the task's session,
                or is changing ``status`` on a task whose linked Approval
                designates someone else as approver.
        """
        task = await self.get(task_id, caller=caller)
        if data.status is not None and data.status != task.status:
            await self._assert_status_change_allowed(task, caller)
        return await self._repo.update(task_id, data, user_id=caller.id)

    async def delete(self, task_id: str, *, caller: User) -> None:
        """Delete a WorkflowTask.

        Args:
            task_id: Identifier of the task to delete.
            caller: The authenticated user performing the deletion.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not access the task's session.
        """
        await self.get(task_id, caller=caller)
        await self._repo.delete(task_id)
