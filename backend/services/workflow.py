"""Use case service for Workflow resources.

Holds the Workflow read/update/delete operations plus the multi-collaborator
``execute`` orchestration (resolve workflow → resolve skill → create a
WorkflowSession and copy the published task templates into it). Workflows are
not created here: they are born from the generation flow in
``services/workflow_design.py``.

Editing a ``published`` workflow moves it to ``modified``: the live task templates have
drifted from the one approved at publish time, so runs keep using the
``WorkflowPublishedVersion`` snapshot until the workflow is published again or
the edits are dropped through :meth:`WorkflowService.discard_changes`.
"""

import logging
import uuid
from collections.abc import Sequence

from models.user import Role, User, has_role
from models.workflow import Workflow, WorkflowStatus, WorkflowUpdate
from models.workflow_published_version import (
    WorkflowPublishedVersionTemplate,
    parse_templates,
    snapshot_template,
)
from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from models.workflow_task import WorkflowTaskCreate, WorkflowTaskStatus
from repositories import (
    MAX_TASK_TEMPLATES,
    AgentSkillRepository,
    WorkflowPublishedVersionRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import (
    ForbiddenError,
    NotFoundError,
    SkillNotReadyError,
    WorkflowNotDeactivatableError,
    WorkflowNotModifiedError,
    WorkflowNotRunnableError,
)
from repositories.query import FilterSpec, SortSpec

logger = logging.getLogger(__name__)

# Module-level alias for ``list[...]``. ``WorkflowService`` defines a method
# named ``list``, which causes mypy to resolve a bare ``list[...]`` annotation
# in methods declared after it to that method rather than the builtin; the
# alias is evaluated in module scope where ``list`` is unambiguously the
# builtin.
_SnapshotTemplateList = list[WorkflowPublishedVersionTemplate]


def _topo_order(
    templates: Sequence[WorkflowPublishedVersionTemplate],
) -> list[WorkflowPublishedVersionTemplate]:
    """Return the templates ordered so every dependency precedes its dependents.

    Kahn's algorithm seeded in the given (position) order for stability. The
    repository enforces acyclicity when edges are written, so a cycle here is
    impossible; the defensive fallback simply appends any leftovers.

    Args:
        templates: The workflow's task templates.

    Returns:
        The same templates in dependency order.
    """
    by_id = {t.id: t for t in templates}
    indegree = {t.id: 0 for t in templates}
    dependents: dict[str, list[str]] = {t.id: [] for t in templates}
    for template in templates:
        for dep_id in template.depends_on_ids:
            if dep_id in by_id:
                dependents[dep_id].append(template.id)
                indegree[template.id] += 1
    queue = [t.id for t in templates if indegree[t.id] == 0]
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in dependents[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    ordered = [by_id[tid] for tid in order]
    if len(ordered) < len(templates):
        seen = set(order)
        ordered.extend(t for t in templates if t.id not in seen)
    return ordered


class WorkflowService:
    """Application service orchestrating Workflow operations."""

    def __init__(
        self,
        workflows: WorkflowRepository,
        skills: AgentSkillRepository,
        ws_repo: WorkflowSessionRepository,
        templates: WorkflowTaskTemplateRepository,
        tasks: WorkflowTaskRepository,
        versions: WorkflowPublishedVersionRepository,
    ) -> None:
        """Initialize the service.

        Args:
            workflows: Repository providing Workflow persistence.
            skills: Repository providing AgentSkill persistence.
            ws_repo: Repository providing WorkflowSession persistence.
            templates: Repository providing WorkflowTaskTemplate persistence,
                read at execute time to copy the task templates into the new session.
            tasks: Repository providing WorkflowTask persistence, written at
                execute time with the copied tasks.
            versions: Repository holding the snapshot taken at publish time,
                which a ``modified`` workflow runs against and
                :meth:`discard_changes` restores from.
        """
        self._workflows = workflows
        self._skills = skills
        self._ws_repo = ws_repo
        self._templates = templates
        self._tasks = tasks
        self._versions = versions

    async def get(self, workflow_id: str) -> Workflow:
        """Return the Workflow with the given ID.

        Args:
            workflow_id: Identifier of the workflow to fetch.

        Returns:
            The matching Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        return workflow

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Workflow]:
        """Return a page of Workflow records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of workflows.
        """
        return await self._workflows.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def update(
        self, workflow_id: str, data: WorkflowUpdate, *, caller: User
    ) -> Workflow:
        """Apply a partial update to a Workflow, authorizing the acting user.

        Editing a ``published`` workflow moves it to ``modified``, so runs keep
        using the snapshot taken at publish time until it is published again.
        An update that sets no fields changes nothing and leaves the status
        alone.

        ``generated_description`` may only be changed by a ``super_admin``
        (see :class:`~models.workflow.WorkflowUpdate`); every other field
        stays open to any caller who reached this route (gated to the
        ``developer`` role at the router).

        Args:
            workflow_id: Identifier of the workflow to update.
            data: Fields to update.
            caller: The authenticated user performing the update.

        Returns:
            The updated Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForbiddenError: If the update would change ``generated_description``
                and the caller is not a super admin.
        """
        current = await self.get(workflow_id)
        update = data.model_dump(exclude_unset=True)
        if (
            "generated_description" in update
            and update["generated_description"] != current.generated_description
            and not has_role(caller, Role.super_admin)
        ):
            raise ForbiddenError(
                "Only a super admin can edit the generated description"
            )
        updated = await self._workflows.update(workflow_id, data, user_id=caller.id)
        if not update:
            return updated
        await self._workflows.mark_modified(workflow_id, user_id=caller.id)
        # Re-read after the status commit: it expires the instance returned
        # above, and serializing an expired one outside the request's greenlet
        # context would fail.
        return await self.get(workflow_id)

    async def delete(self, workflow_id: str) -> None:
        """Delete a Workflow.

        Args:
            workflow_id: Identifier of the workflow to delete.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        await self._workflows.delete(workflow_id)

    async def execute(self, workflow_id: str, *, caller: User) -> WorkflowSession:
        """Start a workflow run by creating a WorkflowSession with its tasks.

        Resolves the workflow and its skill, records a new WorkflowSession
        pinned to the skill's currently published revision, and copies the
        workflow's task templates into the session as ``pending``
        WorkflowTasks (dependency edges and tool bindings included), so later
        template edits never affect this run. The ADK session is created
        lazily on the first agent call, which starts executing immediately —
        the tasks were approved by publishing the workflow (or, for a
        ``developer``/``super_admin`` caller, is still being tested pre-publish).

        A ``modified`` workflow runs its **last published version**: name,
        description, and task templates all come from the snapshot taken at
        publish time, not from the edited live rows. Publishing again is what
        promotes the edits into runs.

        No cloning happens here: the skill's repository was published into the
        shared store when it was registered (and re-published by each pull), so
        a run only has to name the revision it starts against. A skill with no
        published revision — its clone is still running, or it failed — cannot
        be run at all.

        Args:
            workflow_id: Identifier of the workflow to execute.
            caller: The authenticated user starting the run. A ``draft``
                workflow is only runnable when this user holds the
                ``developer`` role (``super_admin`` bypasses via
                :func:`~models.user.has_role`); ``published`` and ``modified``
                workflows are runnable by any caller who reached this route
                (role-gated to ``requester``/``developer`` at the router).

        Returns:
            The created WorkflowSession.

        Raises:
            NotFoundError: If the workflow or its skill does not exist.
            WorkflowNotRunnableError: If the workflow is neither ``published``
                nor ``modified`` (and, for a non-``developer`` caller, not
                ``draft`` either), or has no task templates.
            SkillNotReadyError: If the skill has no published revision yet.
        """
        workflow = await self.get(workflow_id)
        runnable = workflow.status in (
            WorkflowStatus.published,
            WorkflowStatus.modified,
        ) or (
            workflow.status is WorkflowStatus.draft and has_role(caller, Role.developer)
        )
        if not runnable:
            raise WorkflowNotRunnableError(
                workflow_id, "only published workflows can be executed"
            )
        skill = await self._skills.get(workflow.agent_skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", workflow.agent_skill_id)
        if skill.commit_sha is None:
            raise SkillNotReadyError(skill.id)
        name, description, templates = await self._resolve_design(workflow)
        if not templates:
            raise WorkflowNotRunnableError(workflow_id, "it has no task templates")

        user = caller.id or "user"
        session_id = str(uuid.uuid4())

        ws_create = WorkflowSessionCreate(
            session_id=session_id,
            workflow_name=name,
            workflow_description=description,
            agent_skill_id=skill.id,
            agent_skill_name=skill.name,
            agent_skill_repo_url=skill.repo_url,
            agent_skill_repo_path=skill.repo_path,
            agent_skill_commit_sha=skill.commit_sha,
            initiator_id=user,
        )
        ws = await self._ws_repo.create(
            ws_create, workflow_id=workflow.id, user_id=user
        )
        ws_id = ws.id

        # Copy the task templates in dependency order, remapping template ids to the
        # freshly created task ids so the edges land on the copies.
        template_to_task: dict[str, str] = {}
        for template in _topo_order(templates):
            task = await self._tasks.create(
                WorkflowTaskCreate(
                    workflow_session_id=ws_id,
                    title=template.title,
                    description=template.description,
                    status=WorkflowTaskStatus.pending,
                    position=template.position,
                    depends_on_ids=[
                        template_to_task[dep_id]
                        for dep_id in template.depends_on_ids
                        if dep_id in template_to_task
                    ],
                    tool_bindings=template.tool_bindings,
                ),
                user_id=user,
            )
            template_to_task[template.id] = task.id
        # Re-read after the last commit: each task commit on the shared request
        # session expires the ``ws`` instance, and serializing an expired one
        # outside the request's greenlet context would fail.
        created = await self._ws_repo.get(ws_id)
        if created is None:  # pragma: no cover - just created above
            raise NotFoundError("WorkflowSession", ws_id)
        return created

    async def _resolve_design(
        self, workflow: Workflow
    ) -> tuple[str, str | None, _SnapshotTemplateList]:
        """Return the name, description, and task templates a run should use.

        A ``modified`` workflow runs its last published snapshot; every other
        status runs the live rows (for ``published`` the two are identical by
        construction). A ``modified`` workflow without a snapshot should not
        exist — the status is only reachable from ``published``, which always
        writes one — so that case is logged and falls back to the live task templates
        rather than refusing to run.

        Args:
            workflow: The workflow being executed.

        Returns:
            The workflow name, description, and task templates to copy.
        """
        if workflow.status is WorkflowStatus.modified:
            version = await self._versions.get(workflow.id)
            if version is not None:
                return version.name, version.description, parse_templates(version)
            logger.warning(
                "Workflow %s is 'modified' but has no published snapshot; "
                "running its current task templates instead.",
                workflow.id,
            )
        live = await self._templates.list(
            limit=MAX_TASK_TEMPLATES, offset=0, workflow_id=workflow.id
        )
        return (
            workflow.name,
            workflow.effective_description,
            [snapshot_template(t) for t in live],
        )

    async def discard_changes(self, workflow_id: str, *, user_id: str) -> Workflow:
        """Drop a ``modified`` workflow's edits and restore its published version.

        Rewrites the workflow's task templates from the snapshot taken at
        publish time (reusing the original template IDs), restores the name and
        description recorded alongside them, and returns the workflow to
        ``published``. Runs already started are untouched — they copied their
        task templates when they began.

        Args:
            workflow_id: Identifier of the workflow to restore.
            user_id: ID of the user discarding the changes.

        Returns:
            The restored Workflow, back in ``published``.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            WorkflowNotModifiedError: If the workflow has no unpublished
                changes — it is not ``modified``, or has no snapshot to
                restore.
            ForeignKeyViolationError: If the snapshot binds an MCP tool on a
                server that has since been deleted.
        """
        workflow = await self.get(workflow_id)
        if workflow.status is not WorkflowStatus.modified:
            raise WorkflowNotModifiedError(workflow_id)
        version = await self._versions.get(workflow_id)
        if version is None:  # pragma: no cover - unreachable via publish
            raise WorkflowNotModifiedError(workflow_id)
        # Capture before the commits below: each commit on the shared request
        # session expires loaded instances, and a plain attribute read on an
        # expired instance fails outside an explicit refresh.
        name = version.name
        description = version.description
        templates = parse_templates(version)

        await self._templates.replace_all_for_workflow(
            workflow_id, templates, user_id=user_id
        )
        await self._workflows.update(
            workflow_id,
            WorkflowUpdate(name=name, description=description),
            user_id=user_id,
        )
        return await self._workflows.set_status(
            workflow_id, WorkflowStatus.published, user_id=user_id
        )

    async def deactivate(self, workflow_id: str, *, user_id: str) -> Workflow:
        """Return a published workflow to draft, revoking requester execute access.

        Only ``published`` or ``modified`` workflows can be deactivated. The
        workflow's task templates, description, and any published snapshot are
        left untouched — deactivating only changes ``status``, so the workflow
        can be published again later exactly as it was, and a developer can
        keep executing/adjusting it in the meantime (draft workflows remain
        runnable by developer/super_admin — see :meth:`execute`).

        Args:
            workflow_id: Identifier of the workflow to deactivate.
            user_id: ID of the user deactivating the workflow.

        Returns:
            The deactivated Workflow, now ``draft``.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            WorkflowNotDeactivatableError: If the workflow is not
                ``published`` or ``modified``.
        """
        workflow = await self.get(workflow_id)
        if workflow.status not in (WorkflowStatus.published, WorkflowStatus.modified):
            raise WorkflowNotDeactivatableError(workflow_id)
        return await self._workflows.set_status(
            workflow_id, WorkflowStatus.draft, user_id=user_id
        )
