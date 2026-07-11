"""Use case service for WorkflowTask resources.

Wraps the :class:`WorkflowTaskRepository` with the business rules the router
needs: raising :class:`NotFoundError` when a task is missing and authorizing
every operation against the task's parent workflow session — only the session
owner, a designated approver of the session, or a super admin may read or
modify a session's tasks.
"""

from models.user import User
from models.workflow_task import (
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)
from repositories import WorkflowSessionRepository, WorkflowTaskRepository
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from services.workflow_session_access import WorkflowSessionAccessPolicy


class WorkflowTaskService:
    """Application service orchestrating WorkflowTask operations."""

    def __init__(
        self,
        repo: WorkflowTaskRepository,
        ws_repo: WorkflowSessionRepository,
        access: WorkflowSessionAccessPolicy,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTask persistence.
            ws_repo: Repository used to resolve a task's parent session for
                the access check.
            access: Policy restricting task operations to the session owner,
                the session's designated approvers, and super admins.
        """
        self._repo = repo
        self._ws_repo = ws_repo
        self._access = access

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

        Args:
            task_id: Identifier of the task to update.
            data: Fields to update.
            caller: The authenticated user performing the update.

        Returns:
            The updated WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not access the task's session.
        """
        await self.get(task_id, caller=caller)
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
