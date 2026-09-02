"""Use case service for WorkflowTaskTemplate resources.

Wraps the repository for the manual template-editing endpoints (the admin UI's
workflow template editor). Authorization is role-based only — template writes are
developer-gated at the route — because templates belong to a workflow, not to a
per-user session.

Every write here also settles the parent workflow's status through
``mark_design_edited``: a ``published`` workflow moves to ``modified`` (the
task templates have drifted from the snapshot taken at publish time, and runs
keep using that snapshot until the workflow is published again), and one left
``failed`` by its design run recovers to ``draft``, since rebuilding the
templates is what repairs a failed design. The design agent's tools
(``infrastructure/design_task_tools.py``) go straight to the repository, so
they make the same call themselves — task templates refined by chat are no
more published, and no more broken, than ones edited here.
"""

import builtins
from collections.abc import Collection, Sequence

from models.user import Role, has_any_role
from models.workflow import Workflow, WorkflowStatus
from models.workflow_published_version import parse_templates, published_template_read
from models.workflow_task_template import (
    WorkflowTaskTemplateCreate,
    WorkflowTaskTemplateRead,
    WorkflowTaskTemplateUpdate,
)
from repositories import (
    WorkflowPublishedVersionRepository,
    WorkflowRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class WorkflowTaskTemplateService:
    """Application service orchestrating WorkflowTaskTemplate operations."""

    def __init__(
        self,
        repo: WorkflowTaskTemplateRepository,
        workflows: WorkflowRepository,
        versions: WorkflowPublishedVersionRepository,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTaskTemplate persistence.
            workflows: Repository used to 404 template listings of a
                nonexistent workflow, and to settle the parent workflow's
                status after a write.
            versions: Repository holding the snapshot taken at publish time,
                which is what a non-``developer`` reads while the workflow is
                ``modified``.
        """
        self._repo = repo
        self._workflows = workflows
        self._versions = versions

    @staticmethod
    def _reads_snapshot(workflow: Workflow, caller_roles: Collection[str]) -> bool:
        """Return whether this caller is served the published snapshot.

        Args:
            workflow: The parent workflow.
            caller_roles: The caller's effective roles.

        Returns:
            ``True`` when the workflow is ``modified`` and the caller is not a
            ``developer`` (nor, via the bypass, a ``super_admin``).
        """
        return workflow.status is WorkflowStatus.modified and not has_any_role(
            caller_roles, Role.developer
        )

    async def _get_live(self, template_id: str) -> WorkflowTaskTemplateRead:
        """Return the live template row, whatever its workflow's status.

        The write paths below read back what they just wrote, so they must see
        the row itself rather than the published view :meth:`get` serves.

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

    async def get(
        self, template_id: str, *, caller_roles: Collection[str]
    ) -> WorkflowTaskTemplateRead:
        """Return the template with the given ID.

        A caller who is not a ``developer`` reads the template as it was
        published: while its workflow is ``modified``, the live row describes an
        unapproved edit, so the snapshot's copy is returned instead. A template
        added since the last publish has no such copy and is reported as
        missing, exactly as it would be if the caller had never learned its id.

        Args:
            template_id: Identifier of the template to fetch.
            caller_roles: The caller's effective roles.

        Returns:
            The matching template.

        Raises:
            NotFoundError: If no template exists with the given ID, if its
                workflow is not visible to this caller, or if the caller reads
                the snapshot and it holds no such template.
        """
        template = await self._repo.get(template_id)
        if template is None:
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        workflow = await self._workflows.get(template.workflow_id)
        if workflow is None:
            # Unreachable while the cascade holds; a template whose workflow
            # cannot be read is not one to serve either.
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        if not self._reads_snapshot(workflow, caller_roles):
            return template
        version = await self._versions.get(workflow.id)
        published = {t.id: t for t in parse_templates(version)} if version else {}
        if template_id not in published:
            raise NotFoundError("WorkflowTaskTemplate", template_id)
        return published_template_read(published[template_id], workflow=workflow)

    async def list_for_workflow(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        caller_roles: Collection[str] = (),
    ) -> builtins.list[WorkflowTaskTemplateRead]:
        """Return the task templates belonging to a workflow.

        A caller who is not a ``developer`` is served the templates recorded in
        the workflow's published snapshot whenever it is ``modified`` — the same
        design its runs use. Paging, sorting, and filtering mean the same thing
        on either source; see
        ``repositories.workflow_published_version.SqlWorkflowPublishedVersionRepository.list_templates``.

        Args:
            workflow_id: Identifier of the parent workflow.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            caller_roles: The caller's effective roles.

        Returns:
            The requested page of templates for the workflow.

        Raises:
            NotFoundError: If the parent workflow does not exist, so callers
                can distinguish "no such workflow" from "workflow has no
                templates".
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        if not self._reads_snapshot(workflow, caller_roles):
            return await self._repo.list(
                limit=limit,
                offset=offset,
                workflow_id=workflow_id,
                sort=sort,
                filters=filters,
            )
        published = await self._versions.list_templates(
            workflow_id, limit=limit, offset=offset, sort=sort, filters=filters
        )
        return [published_template_read(t, workflow=workflow) for t in published]

    async def create(
        self, data: WorkflowTaskTemplateCreate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Create a new template belonging to the workflow named in ``data``.

        Moves a ``published`` parent workflow to ``modified``, and recovers a
        ``failed`` one to ``draft``.

        Args:
            data: Fields for the new template.
            user_id: ID of the user creating the template.

        Returns:
            The created template.
        """
        template = await self._repo.create(data, user_id=user_id)
        # Capture before the status commit expires the instance: reading an
        # expired attribute outside the request's greenlet context would fail.
        template_id = template.id
        await self._workflows.mark_design_edited(data.workflow_id, user_id=user_id)
        return await self._get_live(template_id)

    async def update(
        self, template_id: str, data: WorkflowTaskTemplateUpdate, *, user_id: str
    ) -> WorkflowTaskTemplateRead:
        """Apply a partial update to a template.

        Moves a ``published`` parent workflow to ``modified``, and recovers a
        ``failed`` one to ``draft``.

        Args:
            template_id: Identifier of the template to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated template.

        Raises:
            NotFoundError: If no template exists with the given ID.
        """
        updated = await self._repo.update(template_id, data, user_id=user_id)
        workflow_id = updated.workflow_id
        await self._workflows.mark_design_edited(workflow_id, user_id=user_id)
        return await self._get_live(template_id)

    async def delete(self, template_id: str, *, user_id: str) -> None:
        """Delete a template.

        Moves a ``published`` parent workflow to ``modified``, and recovers a
        ``failed`` one to ``draft``.

        Args:
            template_id: Identifier of the template to delete.
            user_id: ID of the user deleting the template.

        Raises:
            NotFoundError: If no template exists with the given ID.
        """
        template = await self._get_live(template_id)
        workflow_id = template.workflow_id
        await self._repo.delete(template_id)
        await self._workflows.mark_design_edited(workflow_id, user_id=user_id)
