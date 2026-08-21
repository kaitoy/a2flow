"""Workflow generation ("Generate workflow") and publication use cases.

``WorkflowDesignService.generate`` registers a draft Workflow synchronously,
minting the id of the design session it will be designed in; the actual design
run — :func:`generate_workflow_design` — runs as a background job because it is
a full agent run against an LLM and must not hold the HTTP request open. The job
drives the ``initial_design`` agent through the same ``ADKAgent`` machinery
the chat endpoints use, so the prompt and the agent's reply land in the same
ADK session the design chat later reopens.

``WorkflowDesignService.publish`` gates execution: it freezes the current
design into a ``WorkflowPublishedVersion`` snapshot and marks the workflow
``published``. Later edits move it to ``modified`` and keep running against
that snapshot until it is published again. Publishing runs no LLM of its own —
re-summarizing the design conversation is a separate, user-triggered step
(``WorkflowDesignService.generate_description``).
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from ag_ui.core import RunAgentInput, RunErrorEvent, UserMessage
from google.adk.sessions import BaseSessionService

from infrastructure.agent import (
    USER_ID_PROP_KEY,
    AgentKind,
    AgentRegistry,
    tenant_app_name,
)
from infrastructure.locks import advisory_lock, agent_run_key
from infrastructure.skill_manager import SkillManager
from infrastructure.summarizer import (
    build_design_transcript,
    summarize_design_transcript,
)
from models.notification import NotificationCreate, NotificationType
from models.workflow import (
    Workflow,
    WorkflowCreate,
    WorkflowRead,
    WorkflowStatus,
    WorkflowUpdate,
)
from models.workflow_published_version import dump_templates, snapshot_template
from repositories import (
    MAX_TASK_TEMPLATES,
    AgentSkillRepository,
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
from services.workflow import build_workflow_read

logger = logging.getLogger(__name__)

#: Signature of the summarizer, injectable for tests.
Summarizer = Callable[[str], Awaitable[str]]

#: Signature of the background design job as the router hands it to
#: ``BackgroundTasks``.
WorkflowGenerationJob = Callable[..., Awaitable[None]]

#: Failure reason recorded when the run completed without registering anything.
NO_TASK_TEMPLATES_REASON = "The design run registered no task templates."

#: Failure reason recorded when no runnable revision of the skill is on disk.
SKILL_NOT_READY_REASON = "The agent skill has no usable published revision."

#: Failure reason recorded when the workflow or its skill has vanished.
MISSING_RECORD_REASON = "The workflow or its agent skill no longer exists."

#: Failure reason recorded for a crash with no more specific classification.
UNEXPECTED_FAILURE_REASON = (
    "The design run failed unexpectedly. Check the server log for details."
)


def _agent_run_failed_reason(code: str | None) -> str:
    """Return the reason to record when the design agent reports a run error.

    The event's ``message`` is the raw text the model provider produced, so it
    is logged server-side only — the row keeps a fixed summary plus the event's
    coarse ``code`` (``EXECUTION_ERROR``, ``EXECUTION_TIMEOUT``, ...), which
    names the failure class without putting the provider's wording in the UI.

    Args:
        code: The ``RunErrorEvent`` code, or ``None`` when it carries none.

    Returns:
        The summary to store as the workflow's ``generation_error``.
    """
    suffix = f" ({code})" if code else ""
    return f"The design agent run failed{suffix}. Check the server log for details."


def _crash_reason(exc: Exception) -> str:
    """Return the reason to record for an exception raised by the design run.

    Failures the user can act on get a message naming what to fix; anything
    else gets a fixed summary, leaving the raw exception text to the log.

    Args:
        exc: The exception that ended the run.

    Returns:
        The summary to store as the workflow's ``generation_error``.
    """
    if isinstance(exc, SkillNotReadyError):
        return SKILL_NOT_READY_REASON
    if isinstance(exc, NotFoundError):
        return MISSING_RECORD_REASON
    return UNEXPECTED_FAILURE_REASON


class WorkflowDesignService:
    """Registers draft workflows from skills and publishes adjusted designs."""

    def __init__(
        self,
        workflows: WorkflowRepository,
        skills: AgentSkillRepository,
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
            templates: Repository providing WorkflowTaskTemplate persistence.
            versions: Repository storing the published-design snapshot written by
                :meth:`publish`.
            session_service: ADK session store, read by
                :meth:`generate_description` to build the design transcript.
            app_name: ADK application name keying sessions in the store.
            summarize: One-shot summarizer turning the transcript into the
                workflow's ``generated_description``; injectable for tests.
                Defaults to :func:`~infrastructure.summarizer.summarize_design_transcript`,
                resolved here rather than as a parameter default so a test that
                monkeypatches the module attribute reaches the service the
                request-scoped factory builds.
        """
        self._workflows = workflows
        self._skills = skills
        self._templates = templates
        self._versions = versions
        self._session_service = session_service
        self._app_name = app_name
        self._summarize = summarize or summarize_design_transcript

    async def generate(self, skill_id: str, name: str, *, user_id: str) -> Workflow:
        """Register a draft Workflow, with its design session, for a skill.

        Creates the workflow in ``generating`` status, minting the id of the
        design session it will be designed in and pinning it to the skill's
        current published revision, then returns; the caller schedules
        :func:`generate_workflow_design` as a background job to fill in the
        task templates. The prompt itself is not stored — it becomes the design
        session's first chat message. The workflow also inherits the skill's
        tag attachments as a one-time copy at creation time; the two records'
        tags are independent from then on.

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
            WorkflowCreate(
                name=name,
                agent_skill_id=skill_id,
                session_id=str(uuid.uuid4()),
                agent_skill_commit_sha=commit_sha,
            ),
            user_id=user_id,
        )
        workflow_id = workflow.id
        tag_ids = await self._skills.tag_ids_for(skill_id)
        if tag_ids:
            await self._workflows.set_tags(workflow_id, tag_ids)
        await self._workflows.set_status(
            workflow_id, WorkflowStatus.generating, user_id=user_id
        )
        # Re-read after the last commit: each commit on the shared request
        # session expires loaded instances, and serializing an expired one
        # outside the request's greenlet context would fail.
        created = await self._workflows.get(workflow_id)
        if created is None:  # pragma: no cover - just created above
            raise NotFoundError("Workflow", workflow_id)
        return created

    async def to_read(self, workflow: Workflow) -> WorkflowRead:
        """Project one Workflow into its API read view, attaching its tags.

        Shares :func:`services.workflow.build_workflow_read` with
        :class:`services.workflow.WorkflowService` so a workflow serializes
        identically whichever service returned it.

        Args:
            workflow: The persisted workflow to project.

        Returns:
            The read view, with tag ids attached.
        """
        return await build_workflow_read(self._workflows, workflow)

    async def publish(self, workflow_id: str, *, user_id: str) -> Workflow:
        """Publish a workflow, making it executable.

        Requires the design to be settled and worth promoting: generation must
        not be in flight, at least one task template must exist, and the
        workflow must not already be ``published`` — an in-sync snapshot has
        nothing new to freeze, so re-publishing it is rejected rather than
        rewritten. Editing a published workflow moves it to ``modified``, which
        publishes again normally. No LLM runs here — the
        ``generated_description`` is whatever the initial generation job wrote
        or the user last produced through :meth:`generate_description`, so
        publishing is a pure snapshot-and-promote step.

        The workflow's name, effective description (the user's ``description``
        override if set, else its ``generated_description`` — see
        :attr:`~models.workflow.Workflow.effective_description`), and full
        task-template list are frozen into its ``WorkflowPublishedVersion``
        snapshot, replacing the previous one. Runs started while the workflow
        is ``modified`` use that snapshot instead of the live templates, so a
        published design keeps executing exactly as it was approved.

        Args:
            workflow_id: Identifier of the workflow to publish.
            user_id: ID of the user publishing the workflow.

        Returns:
            The published Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            WorkflowNotRunnableError: If generation is still in progress, the
                workflow is already ``published`` (its snapshot is in sync, so
                re-publishing would only rewrite it with identical content), or
                it has no task templates.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        if workflow.status is WorkflowStatus.generating:
            raise WorkflowNotRunnableError(
                workflow_id, "the design run is still in progress"
            )
        if workflow.status is WorkflowStatus.published:
            raise WorkflowNotRunnableError(
                workflow_id, "it is already published with no changes to promote"
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
        """Re-summarize a workflow's design conversation into its description.

        The on-demand half of the AI summary: the initial generation job writes
        ``generated_description`` once, and this method rewrites it whenever the
        user asks for it — after adjusting the task templates through the design chat,
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
                progress, or the workflow has no design conversation to
                summarize.
            SummarizationFailedError: If the summarizer LLM call fails.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError("Workflow", workflow_id)
        if workflow.status is WorkflowStatus.generating:
            raise WorkflowDescriptionNotGeneratableError(
                workflow_id, "its task templates are still generating"
            )
        transcript = await self._design_transcript(workflow_id)
        if not transcript:
            raise WorkflowDescriptionNotGeneratableError(
                workflow_id, "it has no design conversation to summarize"
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

    async def _design_transcript(self, workflow_id: str) -> str:
        """Return the workflow's design conversation as plain text.

        Args:
            workflow_id: Identifier of the workflow whose conversation to read.

        Returns:
            The transcript, or an empty string when the workflow does not exist
            or its design session's ADK session has not been created yet.
        """
        workflow = await self._workflows.get(workflow_id)
        if workflow is None:
            return ""
        session = await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, workflow.tenant_id),
            user_id=workflow.created_by,
            session_id=workflow.session_id,
        )
        if session is None:
            return ""
        return build_design_transcript(session.events)


async def generate_workflow_design(
    workflow_id: str,
    prompt: str,
    *,
    user_id: str,
    registry: AgentRegistry,
    session_service: BaseSessionService,
    skills_store: SkillManager,
    app_name: str,
) -> None:
    """Run the unattended design agent that fills in a workflow's templates.

    The background half of "Generate workflow". Sends ``prompt`` as the user
    message of the workflow's design session and drives the
    ``initial_design`` agent to completion; the agent registers the task
    templates through its design tools. Afterwards the conversation is
    summarized into the workflow's ``generated_description``, the status
    becomes ``draft``, and a ``workflow_draft_ready`` notification is sent to
    the generating user. Like the skill sync job, this function never raises.

    Any failure lands on the row as ``status=failed`` plus a reason (which the
    admin UI and the design chat both show) and raises a
    ``workflow_generation_failed`` notification. Three kinds of failure reach
    that path, and the agent run is the subtle one: ``ADKAgent`` turns an LLM
    error into a ``RunErrorEvent`` in the stream instead of raising, so the
    loop below inspects the events rather than relying on ``except``. A run
    that errors is failed even if it managed to register templates first — a
    half-designed workflow handed over as ``draft`` would misreport itself as
    complete. The templates and the design conversation survive either way, so
    the user can carry on in the design chat or generate again. Recorded
    reasons are fixed summaries; the raw provider/exception text is logged
    server-side only.

    Opens its own database sessions (the request-scoped one is closed by the
    time it runs). Collaborators that are process-wide singletons (registry,
    session service, skill store, app name) are passed in by the DI factory
    that builds the job.

    Args:
        workflow_id: Identifier of the workflow to design.
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
        SqlWorkflowRepository,
        SqlWorkflowTaskTemplateRepository,
    )
    from repositories.tenant_bootstrap import resolve_workflow_tenant
    from services.notification_dispatch import build_notification_dispatcher

    async with AsyncSession(database.engine, expire_on_commit=False) as db:
        tenant_id = await resolve_workflow_tenant(db, workflow_id)
    if tenant_id is None:
        logger.warning(
            "Plan generation for workflow %s failed: workflow not found.",
            workflow_id,
        )
        return

    async def _set_failed(reason: str) -> None:
        """Record the failure on the workflow and notify the triggering user.

        Every failure path funnels through here, so the row and the bell stay
        in step. The notification is addressed to ``user_id`` rather than the
        workflow's ``created_by`` because the workflow row may be exactly what
        could not be loaded; the two are the same person in practice.

        Args:
            reason: Summarized failure reason to store and show. Raw failure
                text belongs in the log, not here.
        """
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
                await build_notification_dispatcher(db, tenant_id=tenant_id).create(
                    NotificationCreate(
                        user_id=user_id,
                        type=NotificationType.workflow_generation_failed,
                        title="Workflow generation failed",
                        body=reason,
                        workflow_id=workflow_id,
                    ),
                    user_id=user_id,
                )
            except Exception:
                logger.exception(
                    "failed to create workflow_generation_failed notification "
                    "for workflow %s",
                    workflow_id,
                )

    try:
        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            skills = SqlAgentSkillRepository(db, tenant_id=tenant_id)
            workflow = await SqlWorkflowRepository(db, skills, tenant_id=tenant_id).get(
                workflow_id
            )
            if workflow is None:
                raise NotFoundError("Workflow", workflow_id)
            skill = await skills.get(workflow.agent_skill_id)
            if skill is None:
                raise NotFoundError("AgentSkill", workflow.agent_skill_id)
            # Capture before the session closes: the design session's ADK
            # coordinates are read again after every commit below.
            session_id = workflow.session_id
            owner_id = workflow.created_by
            commit_sha = workflow.agent_skill_commit_sha

        skill_dir = skills_store.skill_dir(skill, commit_sha)
        if not skill_dir.exists():
            raise SkillNotReadyError(skill.id)
        scoped_app_name = tenant_app_name(app_name, tenant_id)
        agent = registry.get(
            skill.id,
            commit_sha,
            skill_dir,
            tenant_id=tenant_id,
            kind=AgentKind.initial_design,
        )

        input_data = RunAgentInput(
            thread_id=session_id,
            run_id=str(uuid.uuid4()),
            state=None,
            messages=[UserMessage(id=str(uuid.uuid4()), role="user", content=prompt)],
            tools=[],
            context=[],
            forwarded_props={USER_ID_PROP_KEY: owner_id},
        )
        run_error: RunErrorEvent | None = None
        async with advisory_lock(agent_run_key(scoped_app_name, owner_id, session_id)):
            async for event in agent.run(input_data):
                # ``ADKAgent`` never raises an LLM failure — it yields it as a
                # ``RunErrorEvent`` and ends the stream normally. Keeping the
                # first one preserves the root cause (later events, if any, are
                # cascades), and the loop still drains so the agent's own
                # session-persistence cleanup runs.
                if isinstance(event, RunErrorEvent) and run_error is None:
                    run_error = event

        if run_error is not None:
            logger.warning(
                "The design run of workflow %s reported %s: %s",
                workflow_id,
                run_error.code or "an error",
                run_error.message,
            )
            await _set_failed(_agent_run_failed_reason(run_error.code))
            return

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
            await _set_failed(NO_TASK_TEMPLATES_REASON)
            return

        session = await session_service.get_session(
            app_name=scoped_app_name, user_id=owner_id, session_id=session_id
        )
        transcript = build_design_transcript(session.events) if session else ""
        generated_description: str | None
        try:
            generated_description = await summarize_design_transcript(transcript)
        except Exception:
            logger.warning(
                "Failed to summarize the design conversation of workflow %s; "
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
                await build_notification_dispatcher(db, tenant_id=tenant_id).create(
                    NotificationCreate(
                        user_id=owner_id,
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
            await _set_failed(_crash_reason(exc))
        except Exception:
            logger.exception(
                "failed to record generation failure on workflow %s", workflow_id
            )
