"""Workflow generation ("Generate workflow") and publication use cases.

``WorkflowPlanningService.generate`` registers a draft Workflow plus its
PlanningSession synchronously; the actual plan generation —
:func:`generate_workflow_plan` — runs as a background job because it is a full
agent run against an LLM and must not hold the HTTP request open. The job
drives the ``initial_planning`` agent through the same ``ADKAgent`` machinery
the chat endpoints use, so the prompt and the agent's reply land in the same
ADK session the planning chat later reopens.

``WorkflowPlanningService.publish`` gates execution: it freezes the current
plan into a ``WorkflowPublishedVersion`` snapshot and marks the workflow
``published``. Later edits move it to ``modified`` and keep running against
that snapshot until it is published again. Publishing runs no LLM of its own —
re-summarizing the planning conversation is a separate, user-triggered step
(``WorkflowPlanningService.generate_description``).
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from ag_ui.core import RunAgentInput, UserMessage
from google.adk.sessions import BaseSessionService

from infrastructure.agent import (
    USER_ID_PROP_KEY,
    AgentKind,
    AgentRegistry,
    tenant_app_name,
)
from infrastructure.locks import advisory_lock, agent_run_key
from infrastructure.skill_manager import SkillManager
from infrastructure.summarizer import summarize_planning_transcript
from models.notification import NotificationCreate, NotificationType
from models.planning_session import PlanningSessionCreate
from models.workflow import Workflow, WorkflowCreate, WorkflowStatus, WorkflowUpdate
from models.workflow_published_version import dump_templates, snapshot_template
from repositories import (
    MAX_TASK_TEMPLATES,
    AgentSkillRepository,
    PlanningSessionRepository,
    WorkflowPublishedVersionRepository,
    WorkflowRepository,
    WorkflowTaskTemplateRepository,
)
from repositories.exceptions import (
    NotFoundError,
    SkillNotReadyError,
    SummarizationFailedError,
    WorkflowDescriptionNotGeneratableError,
    WorkflowNotRunnableError,
)
from services.planning_session import build_planning_transcript

logger = logging.getLogger(__name__)

#: Signature of the summarizer, injectable for tests.
Summarizer = Callable[[str], Awaitable[str]]

#: Signature of the background plan-generation job as the router hands it to
#: ``BackgroundTasks``.
WorkflowGenerationJob = Callable[..., Awaitable[None]]


class WorkflowPlanningService:
    """Registers draft workflows from skills and publishes adjusted plans."""

    def __init__(
        self,
        workflows: WorkflowRepository,
        skills: AgentSkillRepository,
        ps_repo: PlanningSessionRepository,
        templates: WorkflowTaskTemplateRepository,
        versions: WorkflowPublishedVersionRepository,
        session_service: BaseSessionService,
        app_name: str,
        summarize: Summarizer | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            workflows: Repository providing Workflow persistence.
            skills: Repository providing AgentSkill persistence.
            ps_repo: Repository providing PlanningSession persistence.
            templates: Repository providing WorkflowTaskTemplate persistence.
            versions: Repository storing the published-plan snapshot written by
                :meth:`publish`.
            session_service: ADK session store, read by
                :meth:`generate_description` to build the planning transcript.
            app_name: ADK application name keying sessions in the store.
            summarize: One-shot summarizer turning the transcript into the
                workflow's ``generated_description``; injectable for tests.
                Defaults to :func:`~infrastructure.summarizer.summarize_planning_transcript`,
                resolved here rather than as a parameter default so a test that
                monkeypatches the module attribute reaches the service the
                request-scoped factory builds.
        """
        self._workflows = workflows
        self._skills = skills
        self._ps_repo = ps_repo
        self._templates = templates
        self._versions = versions
        self._session_service = session_service
        self._app_name = app_name
        self._summarize = summarize or summarize_planning_transcript

    async def generate(self, skill_id: str, name: str, *, user_id: str) -> Workflow:
        """Register a draft Workflow and its PlanningSession for a skill.

        Creates the workflow in ``generating`` status and a planning session
        pinned to the skill's current published revision, then returns; the
        caller schedules :func:`generate_workflow_plan` as a background job to
        fill in the task templates. The prompt itself is not stored — it
        becomes the planning session's first chat message.

        Args:
            skill_id: Identifier of the skill to generate a workflow from.
            name: Unique name of the new workflow.
            user_id: ID of the user generating the workflow.

        Returns:
            The created Workflow (status ``generating``).

        Raises:
            NotFoundError: If no skill exists with the given ID.
            SkillNotReadyError: If the skill has no published revision yet.
            UniqueViolationError: If a workflow with ``name`` already exists.
        """
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)
        if skill.commit_sha is None:
            raise SkillNotReadyError(skill.id)
        # Capture before the commits below: each commit on the shared request
        # session expires loaded instances, and a plain attribute read on an
        # expired instance fails outside an explicit refresh.
        commit_sha = skill.commit_sha

        workflow = await self._workflows.create(
            WorkflowCreate(name=name, agent_skill_id=skill_id), user_id=user_id
        )
        workflow_id = workflow.id
        await self._workflows.set_status(
            workflow_id, WorkflowStatus.generating, user_id=user_id
        )
        await self._ps_repo.create(
            PlanningSessionCreate(
                session_id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                agent_skill_id=skill_id,
                agent_skill_commit_sha=commit_sha,
                user_id=user_id or "user",
            ),
            user_id=user_id,
        )
        # Re-read after the last commit: each commit on the shared request
        # session expires loaded instances, and serializing an expired one
        # outside the request's greenlet context would fail.
        created = await self._workflows.get(workflow_id)
        if created is None:  # pragma: no cover - just created above
            raise NotFoundError("Workflow", workflow_id)
        return created

    async def publish(self, workflow_id: str, *, user_id: str) -> Workflow:
        """Publish a workflow, making it executable.

        Requires the plan to be settled: generation must not be in flight and
        at least one task template must exist. No LLM runs here — the
        ``generated_description`` is whatever the initial generation job wrote
        or the user last produced through :meth:`generate_description`, so
        publishing is a pure snapshot-and-promote step.

        The workflow's name, effective description (the user's ``description``
        override if set, else its ``generated_description`` — see
        :attr:`~models.workflow.Workflow.effective_description`), and full
        task-template list are frozen into its ``WorkflowPublishedVersion``
        snapshot, replacing the previous one. Runs started while the workflow
        is ``modified`` use that snapshot instead of the live templates, so a
        published plan keeps executing exactly as it was approved.

        Args:
            workflow_id: Identifier of the workflow to publish.
            user_id: ID of the user publishing the workflow.

        Returns:
            The published Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            WorkflowNotRunnableError: If generation is still in progress or the
                workflow has no task templates.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        if workflow.status is WorkflowStatus.generating:
            raise WorkflowNotRunnableError(
                workflow_id, "plan generation is still in progress"
            )
        # Capture before the commits below: each commit on the shared request
        # session expires loaded instances, and a plain attribute read on an
        # expired instance fails outside an explicit refresh.
        name = workflow.name
        effective_description = workflow.effective_description
        templates = await self._templates.list(
            limit=MAX_TASK_TEMPLATES, offset=0, workflow_id=workflow_id
        )
        if not templates:
            raise WorkflowNotRunnableError(workflow_id, "it has no task templates")

        await self._versions.upsert(
            workflow_id,
            name=name,
            description=effective_description,
            templates=dump_templates(
                [snapshot_template(t) for t in templates],
            ),
            user_id=user_id,
        )
        return await self._workflows.set_status(
            workflow_id,
            WorkflowStatus.published,
            user_id=user_id,
        )

    async def generate_description(self, workflow_id: str, *, user_id: str) -> Workflow:
        """Re-summarize a workflow's planning conversation into its description.

        The on-demand half of the AI summary: the initial generation job writes
        ``generated_description`` once, and this method rewrites it whenever the
        user asks for it — after adjusting the plan through the planning chat,
        for instance. The summary is persisted immediately, so the caller gets
        back a workflow that already carries it.

        Editing a ``published`` workflow moves it to ``modified`` (a run using
        the workflow's ``description`` fallback would otherwise drift from the
        published snapshot), exactly as a ``PATCH`` of the same field does.

        Args:
            workflow_id: Identifier of the workflow to summarize.
            user_id: ID of the user requesting the summary.

        Returns:
            The updated Workflow, carrying the fresh ``generated_description``.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            WorkflowDescriptionNotGeneratableError: If generation is still in
                progress, or the workflow has no planning conversation to
                summarize.
            SummarizationFailedError: If the summarizer LLM call fails.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        if workflow.status is WorkflowStatus.generating:
            raise WorkflowDescriptionNotGeneratableError(
                workflow_id, "its plan is still generating"
            )
        transcript = await self._planning_transcript(workflow_id)
        if not transcript:
            raise WorkflowDescriptionNotGeneratableError(
                workflow_id, "it has no planning conversation to summarize"
            )
        try:
            summary = await self._summarize(transcript)
        except Exception as e:
            raise SummarizationFailedError(workflow_id, str(e)) from e

        await self._workflows.update(
            workflow_id,
            WorkflowUpdate(generated_description=summary),
            user_id=user_id,
        )
        await self._workflows.mark_modified(workflow_id, user_id=user_id)
        # Re-read after the status commit: it expires the instance returned
        # above, and serializing an expired one outside the request's greenlet
        # context would fail.
        updated = await self._workflows.get(workflow_id)
        if updated is None:  # pragma: no cover - just updated above
            raise NotFoundError("Workflow", workflow_id)
        return updated

    async def _planning_transcript(self, workflow_id: str) -> str:
        """Return the workflow's planning conversation as plain text.

        Args:
            workflow_id: Identifier of the workflow whose conversation to read.

        Returns:
            The transcript, or an empty string when the workflow has no
            planning session or the ADK session does not exist.
        """
        ps = await self._ps_repo.get_by_workflow_id(workflow_id)
        if ps is None:
            return ""
        session = await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, ps.tenant_id),
            user_id=ps.user_id,
            session_id=ps.session_id,
        )
        if session is None:
            return ""
        return build_planning_transcript(session.events)


async def generate_workflow_plan(
    workflow_id: str,
    prompt: str,
    *,
    user_id: str,
    registry: AgentRegistry,
    session_service: BaseSessionService,
    skills_store: SkillManager,
    app_name: str,
) -> None:
    """Run the unattended planning agent that fills in a workflow's templates.

    The background half of "Generate workflow". Sends ``prompt`` as the user
    message of the workflow's planning session and drives the
    ``initial_planning`` agent to completion; the agent registers the task
    templates through its planning tools. Afterwards the conversation is
    summarized into the workflow's ``generated_description``, the status
    becomes ``draft``, and a ``workflow_draft_ready`` notification is sent to
    the generating user. Any failure — including a run that registered no
    templates — lands on the row as ``status=failed`` plus the reason, which
    the admin UI polls; like the skill sync job, this function never raises.

    Opens its own database sessions (the request-scoped one is closed by the
    time it runs). Collaborators that are process-wide singletons (registry,
    session service, skill store, app name) are passed in by the DI factory
    that builds the job.

    Args:
        workflow_id: Identifier of the workflow to plan.
        prompt: The user's request to break into task templates.
        user_id: ID of the user who triggered the generation.
        registry: Registry resolving ADK agents per skill revision and kind.
        session_service: ADK session store shared with the chat endpoints.
        skills_store: Store locating a skill revision's directory on disk.
        app_name: ADK application name keying sessions in the store.
    """
    from sqlmodel.ext.asyncio.session import AsyncSession

    from infrastructure import database
    from repositories import (
        SqlAgentSkillRepository,
        SqlMCPServerRepository,
        SqlNotificationRepository,
        SqlPlanningSessionRepository,
        SqlWorkflowRepository,
        SqlWorkflowTaskTemplateRepository,
    )
    from repositories.tenant_bootstrap import resolve_workflow_tenant

    async with AsyncSession(database.engine, expire_on_commit=False) as db:
        tenant_id = await resolve_workflow_tenant(db, workflow_id)
    if tenant_id is None:
        logger.warning(
            "Plan generation for workflow %s failed: workflow not found.",
            workflow_id,
        )
        return

    async def _set_failed(reason: str) -> None:
        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            workflows = SqlWorkflowRepository(
                db,
                SqlAgentSkillRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            )
            await workflows.set_status(
                workflow_id,
                WorkflowStatus.failed,
                generation_error=reason,
                user_id=user_id,
            )

    try:
        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            skills = SqlAgentSkillRepository(db, tenant_id=tenant_id)
            ps = await SqlPlanningSessionRepository(
                db, tenant_id=tenant_id
            ).get_by_workflow_id(workflow_id)
            if ps is None:
                raise NotFoundError("PlanningSession", workflow_id)
            skill = await skills.get(ps.agent_skill_id)
            if skill is None:
                raise NotFoundError("AgentSkill", ps.agent_skill_id)

        skill_dir = skills_store.skill_dir(skill, ps.agent_skill_commit_sha)
        if not skill_dir.exists():
            raise SkillNotReadyError(skill.id)
        scoped_app_name = tenant_app_name(app_name, tenant_id)
        agent = registry.get(
            skill.id,
            ps.agent_skill_commit_sha,
            skill_dir,
            tenant_id=tenant_id,
            kind=AgentKind.initial_planning,
        )

        input_data = RunAgentInput(
            thread_id=ps.session_id,
            run_id=str(uuid.uuid4()),
            state=None,
            messages=[UserMessage(id=str(uuid.uuid4()), role="user", content=prompt)],
            tools=[],
            context=[],
            forwarded_props={USER_ID_PROP_KEY: ps.user_id},
        )
        async with advisory_lock(
            agent_run_key(scoped_app_name, ps.user_id, ps.session_id)
        ):
            async for _event in agent.run(input_data):
                pass

        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            templates_repo = SqlWorkflowTaskTemplateRepository(
                db,
                SqlWorkflowRepository(
                    db,
                    SqlAgentSkillRepository(db, tenant_id=tenant_id),
                    tenant_id=tenant_id,
                ),
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            )
            templates = await templates_repo.list(
                limit=1, offset=0, workflow_id=workflow_id
            )
        if not templates:
            await _set_failed("The planning run registered no task templates.")
            return

        session = await session_service.get_session(
            app_name=scoped_app_name, user_id=ps.user_id, session_id=ps.session_id
        )
        transcript = build_planning_transcript(session.events) if session else ""
        generated_description: str | None
        try:
            generated_description = await summarize_planning_transcript(transcript)
        except Exception:
            logger.warning(
                "Failed to summarize the planning conversation of workflow %s; "
                "falling back to the transcript head.",
                workflow_id,
                exc_info=True,
            )
            generated_description = transcript[:2000].rstrip() or None

        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            workflows = SqlWorkflowRepository(
                db,
                SqlAgentSkillRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            )
            await workflows.set_status(
                workflow_id,
                WorkflowStatus.draft,
                generated_description=generated_description,
                user_id=user_id,
            )
            try:
                await SqlNotificationRepository(db, tenant_id=tenant_id).create(
                    NotificationCreate(
                        user_id=ps.user_id,
                        type=NotificationType.workflow_draft_ready,
                        title="Workflow draft ready",
                        body="The initial task list has been generated. "
                        "Review it, adjust it if needed, and publish the workflow.",
                        workflow_id=workflow_id,
                    ),
                    user_id=user_id,
                )
            except Exception:
                logger.exception(
                    "failed to create workflow_draft_ready notification "
                    "for workflow %s",
                    workflow_id,
                )
    except Exception as exc:
        logger.warning(
            "Plan generation for workflow %s failed: %s",
            workflow_id,
            exc,
            exc_info=True,
        )
        try:
            await _set_failed(str(exc))
        except Exception:
            logger.exception(
                "failed to record generation failure on workflow %s", workflow_id
            )
