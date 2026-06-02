"""Use case service for WorkflowTask resources.

Wraps the :class:`WorkflowTaskRepository` with the business rules the router
needs (notably raising :class:`NotFoundError` when a task is missing).
"""

from models.workflow_task import (
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)
from repositories import WorkflowTaskRepository
from repositories.exceptions import NotFoundError


class WorkflowTaskService:
    """Application service orchestrating WorkflowTask operations."""

    def __init__(self, repo: WorkflowTaskRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTask persistence.
        """
        self._repo = repo

    async def get(self, task_id: str) -> WorkflowTaskRead:
        """Return the WorkflowTask with the given ID.

        Args:
            task_id: Identifier of the task to fetch.

        Returns:
            The matching WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
        """
        task = await self._repo.get(task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        return task

    async def create(
        self, data: WorkflowTaskCreate, *, user_id: str
    ) -> WorkflowTaskRead:
        """Create a new WorkflowTask.

        Args:
            data: Fields for the new task, including its parent session.
            user_id: ID of the user creating the task.

        Returns:
            The created WorkflowTask.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, user_id: str
    ) -> WorkflowTaskRead:
        """Apply a partial update to a WorkflowTask.

        Args:
            task_id: Identifier of the task to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
        """
        return await self._repo.update(task_id, data, user_id=user_id)

    async def delete(self, task_id: str) -> None:
        """Delete a WorkflowTask.

        Args:
            task_id: Identifier of the task to delete.

        Raises:
            NotFoundError: If no task exists with the given ID.
        """
        await self._repo.delete(task_id)
