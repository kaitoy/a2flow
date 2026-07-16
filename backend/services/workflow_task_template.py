"""Use case service for WorkflowTaskTemplate resources.

Thin wrapper over the repository for the manual template-editing endpoints
(the admin UI's workflow plan editor). Authorization is role-based only —
template writes are developer-gated at the route — because templates belong to
a workflow, not to a per-user session.
"""

import builtins
from collections.abc import Sequence

from models.workflow_task_template import (
    WorkflowTaskTemplateCreate,
    WorkflowTaskTemplateRead,
    WorkflowTaskTemplateUpdate,
)
from repositories import WorkflowRepository, WorkflowTaskTemplateRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class WorkflowTaskTemplateService:
    """Application service orchestrating WorkflowTaskTemplate operations."""

    def __init__(
        self,
        repo: WorkflowTaskTemplateRepository,
        workflows: WorkflowRepository,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTaskTemplate persistence.
            workflows: Repository used to 404 template listings of a
                nonexistent workflow.
        """
        self._repo = repo
        self._workflows = workflows

    async def get(self, template_id: str) -> WorkflowTaskTemplateRead:
        """Return the template with the given ID.

        Args:
            template_id: Identifier of the template to fetch.

        Returns:
            The matching template.

        Raises:
            NotFoundError: If no template exists with the given ID.
        """
        template = await self._repo.get(template_id)
        if template is None:
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        return template

    async def list_for_workflow(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowTaskTemplateRead]:
        """Return the task templates belonging to a workflow.

        Args:
            workflow_id: Identifier of the parent workflow.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of templates for the workflow.

        Raises:
            NotFoundError: If the parent workflow does not exist, so callers
                can distinguish "no such workflow" from "workflow has no
                templates".
        """
        if await self._workflows.get(workflow_id) is None:
            raise NotFoundError("Workflow", workflow_id)
        return await self._repo.list(
            limit=limit,
            offset=offset,
            workflow_id=workflow_id,
            sort=sort,
            filters=filters,
        )

    async def create(
        self, data: WorkflowTaskTemplateCreate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Create a new template belonging to the workflow named in ``data``.

        Args:
            data: Fields for the new template.
            user_id: ID of the user creating the template.

        Returns:
            The created template.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, template_id: str, data: WorkflowTaskTemplateUpdate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Apply a partial update to a template.

        Args:
            template_id: Identifier of the template to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated template.

        Raises:
            NotFoundError: If no template exists with the given ID.
        """
        return await self._repo.update(template_id, data, user_id=user_id)

    async def delete(self, template_id: str) -> None:
        """Delete a template.

        Args:
            template_id: Identifier of the template to delete.

        Raises:
            NotFoundError: If no template exists with the given ID.
        """
        await self._repo.delete(template_id)
