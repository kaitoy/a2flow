"""Use case service for Workflow resources.

Holds the Workflow read/update/delete operations plus the multi-collaborator
``execute`` orchestration (resolve workflow → resolve skill → create a
WorkflowSession and copy the published task templates into it). Workflows are
not created here: they are born from the generation flow in
``services/workflow_planning.py``.
"""

import uuid
from collections.abc import Sequence

from models.workflow import Workflow, WorkflowStatus, WorkflowUpdate
from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from models.workflow_task import WorkflowTaskCreate, WorkflowTaskStatus
from models.workflow_task_template import WorkflowTaskTemplateRead
from repositories import (
    AgentSkillRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import (
    NotFoundError,
    SkillNotReadyError,
    WorkflowNotRunnableError,
)
from repositories.query import FilterSpec, SortSpec


def _topo_order(
    templates: Sequence[WorkflowTaskTemplateRead],
) -> list[WorkflowTaskTemplateRead]:
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
    ) -> None:
        """Initialize the service.

        Args:
            workflows: Repository providing Workflow persistence.
            skills: Repository providing AgentSkill persistence.
            ws_repo: Repository providing WorkflowSession persistence.
            templates: Repository providing WorkflowTaskTemplate persistence,
                read at execute time to copy the plan into the new session.
            tasks: Repository providing WorkflowTask persistence, written at
                execute time with the copied plan.
        """
        self._workflows = workflows
        self._skills = skills
        self._ws_repo = ws_repo
        self._templates = templates
        self._tasks = tasks

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
        self, workflow_id: str, data: WorkflowUpdate, *, user_id: str
    ) -> Workflow:
        """Apply a partial update to a Workflow.

        Args:
            workflow_id: Identifier of the workflow to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        return await self._workflows.update(workflow_id, data, user_id=user_id)

    async def delete(self, workflow_id: str) -> None:
        """Delete a Workflow.

        Args:
            workflow_id: Identifier of the workflow to delete.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        await self._workflows.delete(workflow_id)

    async def execute(self, workflow_id: str, *, user_id: str) -> WorkflowSession:
        """Start a workflow run by creating a WorkflowSession with its tasks.

        Resolves the workflow and its skill, records a new WorkflowSession
        pinned to the skill's currently published revision, and copies the
        workflow's task templates into the session as ``pending``
        WorkflowTasks (dependency edges and tool bindings included), so later
        template edits never affect this run. The ADK session is created
        lazily on the first agent call, which starts executing immediately —
        the plan was approved by publishing the workflow.

        No cloning happens here: the skill's repository was published into the
        shared store when it was registered (and re-published by each pull), so
        a run only has to name the revision it starts against. A skill with no
        published revision — its clone is still running, or it failed — cannot
        be run at all.

        Args:
            workflow_id: Identifier of the workflow to execute.
            user_id: ID of the user starting the run (empty falls back to
                ``"user"``).

        Returns:
            The created WorkflowSession.

        Raises:
            NotFoundError: If the workflow or its skill does not exist.
            WorkflowNotRunnableError: If the workflow is not ``published`` or
                has no task templates.
            SkillNotReadyError: If the skill has no published revision yet.
        """
        workflow = await self.get(workflow_id)
        if workflow.status is not WorkflowStatus.published:
            raise WorkflowNotRunnableError(
                workflow_id, "only published workflows can be executed"
            )
        skill = await self._skills.get(workflow.agent_skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", workflow.agent_skill_id)
        if skill.commit_sha is None:
            raise SkillNotReadyError(skill.id)
        templates = await self._templates.list(
            limit=1000, offset=0, workflow_id=workflow_id
        )
        if not templates:
            raise WorkflowNotRunnableError(workflow_id, "it has no task templates")

        user = user_id or "user"
        session_id = str(uuid.uuid4())

        ws_create = WorkflowSessionCreate(
            session_id=session_id,
            workflow_name=workflow.name,
            workflow_description=workflow.description,
            agent_skill_id=skill.id,
            agent_skill_name=skill.name,
            agent_skill_repo_url=skill.repo_url,
            agent_skill_repo_path=skill.repo_path,
            agent_skill_commit_sha=skill.commit_sha,
            user_id=user,
        )
        ws = await self._ws_repo.create(
            ws_create, workflow_id=workflow.id, user_id=user
        )
        ws_id = ws.id

        # Copy the plan in dependency order, remapping template ids to the
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
