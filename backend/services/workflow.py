"""Use case service for Workflow resources and for their design sessions.

Holds the Workflow read/update/delete operations, the multi-collaborator
``execute`` orchestration (resolve workflow → resolve skill → create a
WorkflowExecution and copy the published task templates into it), and the
workflow's **design session** — the chat its task templates are produced and
refined in. That chat has no record of its own, so it is identified by its
workflow and served here through :meth:`WorkflowService.get_messages` and
:meth:`WorkflowService.resolve_agent`, mirroring how
``services/workflow_execution.py`` serves an execution's workflow session.
Like a workflow session, a design session is shared: every ``developer`` in the
tenant may read and drive it, and each message is attributed to the user who
actually sent it. Sharing follows from the role rather than from a per-record
list of participants, so no separate access policy object is needed — see
:meth:`WorkflowService._assert_design_access`.

Workflows are not created here: they are born from the generation flow in
``services/workflow_design.py``.

Editing a ``published`` workflow moves it to ``modified``: the live task templates have
drifted from the one approved at publish time, so runs keep using the
``WorkflowPublishedVersion`` snapshot until the workflow is published again or
the edits are dropped through :meth:`WorkflowService.discard_changes`.
"""

import builtins
import logging
import secrets
import uuid
from collections.abc import Collection, Sequence
from typing import Any

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.sessions import BaseSessionService, Session

from infrastructure.agent import AgentKind, AgentRegistry, tenant_app_name
from infrastructure.skill_manager import SkillManager
from models.message_meta import MessageScope
from models.user import Role, User, has_any_role
from models.workflow import Workflow, WorkflowRead, WorkflowStatus, WorkflowUpdate
from models.workflow_execution import WorkflowExecution, WorkflowExecutionCreate
from models.workflow_published_version import (
    WorkflowPublishedVersionTemplate,
    parse_templates,
    snapshot_template,
)
from models.workflow_task import WorkflowTaskCreate, WorkflowTaskStatus
from repositories import (
    MAX_TASK_TEMPLATES,
    AgentSkillRepository,
    MessageMetaRepository,
    WorkflowExecutionRepository,
    WorkflowPublishedVersionRepository,
    WorkflowRepository,
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
from services import session_attribution

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

    Kahn's algorithm seeded in the given input order for stability. The
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


#: Alias for ``list[WorkflowRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[WorkflowRead]


async def build_workflow_read(
    workflows: WorkflowRepository, workflow: Workflow
) -> WorkflowRead:
    """Project one Workflow into its API read view, attaching its tags.

    A module-level function rather than a method because two services return
    workflows to the API — this one and
    :class:`services.workflow_design.WorkflowDesignService`, which owns publish,
    deactivate, and the description regeneration — and both need the identical
    projection.

    Args:
        workflows: Repository used to read the workflow's tag attachments.
        workflow: The persisted workflow to project.

    Returns:
        The read view, with tag ids attached.
    """
    return WorkflowRead.from_workflow(
        workflow, tag_ids=await workflows.tag_ids_for(workflow.id)
    )


class WorkflowService:
    """Application service orchestrating Workflow and design-session operations."""

    def __init__(
        self,
        workflows: WorkflowRepository,
        skills: AgentSkillRepository,
        execution_repo: WorkflowExecutionRepository,
        templates: WorkflowTaskTemplateRepository,
        tasks: WorkflowTaskRepository,
        versions: WorkflowPublishedVersionRepository,
        meta: MessageMetaRepository,
        skills_store: SkillManager,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        """Initialize the service.

        Args:
            workflows: Repository providing Workflow persistence.
            skills: Repository providing AgentSkill persistence.
            execution_repo: Repository providing WorkflowExecution persistence.
            templates: Repository providing WorkflowTaskTemplate persistence,
                read at execute time to copy the task templates into the new session.
            tasks: Repository providing WorkflowTask persistence, written at
                execute time with the copied tasks.
            versions: Repository holding the snapshot taken at publish time,
                which a ``modified`` workflow runs against and
                :meth:`discard_changes` restores from.
            meta: Repository recording and reading per-message sender
                attribution for the shared design session.
            skills_store: Store locating a skill revision's directory on disk.
            registry: Registry resolving ADK agents per skill revision and kind.
            session_service: ADK session store holding the design chat history.
            app_name: ADK application name keying sessions in the store.
        """
        self._workflows = workflows
        self._skills = skills
        self._execution_repo = execution_repo
        self._templates = templates
        self._tasks = tasks
        self._versions = versions
        self._meta = meta
        self._skills_store = skills_store
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name

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

    async def get_for_read(
        self, workflow_id: str, *, caller_roles: Collection[str]
    ) -> Workflow:
        """Return the Workflow with the given ID, authorizing draft visibility.

        A ``draft`` workflow can only be created, edited, or executed
        (pre-publish) by a ``developer`` (or, via the ``super_admin`` bypass,
        a ``super_admin``) -- see :meth:`execute`. This extends the same
        restriction to *viewing* it: any other caller (``requester``,
        ``approver``, plain ``admin``) gets a 404 rather than a 403, so a
        draft's existence is never confirmed to someone who couldn't act on
        it, matching ``services.user._assert_tenant_visible``'s convention.

        Args:
            workflow_id: Identifier of the workflow to fetch.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.

        Returns:
            The matching Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID, or it is
                ``draft`` and the caller is not a developer or super admin.
        """
        workflow = await self.get(workflow_id)
        if workflow.status == WorkflowStatus.draft and not has_any_role(
            caller_roles, Role.developer
        ):
            raise NotFoundError("Workflow", workflow_id)
        return workflow

    @staticmethod
    def _assert_design_access(
        workflow: Workflow, caller: User, caller_roles: Collection[str]
    ) -> None:
        """Reject callers with no business in this workflow's design session.

        Designing a workflow is developer work — the same role that gates
        editing and publishing it — so every ``developer`` in the tenant may
        read and drive the chat, just as an execution's approvers share its
        workflow session. ``has_any_role`` lets a ``super_admin`` through. The
        workflow's ``created_by`` is admitted explicitly as well, so the user
        who generated it is not locked out of their own conversation if their
        ``developer`` role is later revoked.

        The tenant boundary is enforced a layer below: the workflow was fetched
        through the tenant-scoped repository, so another tenant's id surfaced as
        404 before ever reaching here.

        Args:
            workflow: The workflow whose design session is being operated on.
            caller: The authenticated user performing the operation.
            caller_roles: The caller's effective roles — direct grants plus
                everything inherited from their groups — so a ``developer``
                held only through a group still admits them.

        Raises:
            ForbiddenError: If the caller is neither a developer, a super admin,
                nor the workflow's creator.
        """
        if caller.id == workflow.created_by or has_any_role(
            caller_roles, Role.developer
        ):
            return
        raise ForbiddenError("Only developers can access this design session")

    async def get_for_design(
        self, workflow_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> Workflow:
        """Return a Workflow, authorizing the caller against its design session.

        Args:
            workflow_id: Identifier of the workflow to fetch.
            caller: The authenticated user requesting the design session.
            caller_roles: The caller's effective roles, including any inherited
                from their groups.

        Returns:
            The matching Workflow.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForbiddenError: If the caller is neither a developer, a super admin,
                nor the workflow's creator.
        """
        workflow = await self.get(workflow_id)
        self._assert_design_access(workflow, caller, caller_roles)
        return workflow

    async def resolve_agent(
        self, workflow_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> tuple[ADKAgent, Workflow]:
        """Resolve the design agent bound to a workflow's design session.

        Mirrors ``WorkflowExecutionService.resolve_agent``: the skill revision
        pinned on the record is loaded from the shared store, falling back to
        the skill's current revision (loudly) when the pinned directory is
        gone, and the agent is resolved with :attr:`AgentKind.design` so the
        chat runs under the interactive design instruction and toolset.

        Args:
            workflow_id: Identifier of the workflow whose agent to resolve.
            caller: The authenticated user driving the agent run.
            caller_roles: The caller's effective roles, including any inherited
                from their groups.

        Returns:
            An ``(agent, workflow)`` tuple.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForbiddenError: If the caller is neither a developer, a super admin,
                nor the workflow's creator.
            SkillNotReadyError: If neither the pinned revision nor the skill's
                current revision is present in the store.
        """
        workflow = await self.get_for_design(
            workflow_id, caller=caller, caller_roles=caller_roles
        )
        skill = await self._skills.get(workflow.agent_skill_id)
        if skill is None:
            raise SkillNotReadyError(workflow.agent_skill_id)

        commit_sha = workflow.agent_skill_commit_sha
        skill_dir = self._skills_store.skill_dir(skill, commit_sha)
        if not skill_dir.exists():
            logger.warning(
                "Skill revision %s of skill %s is missing from the store; "
                "falling back to its current revision %s.",
                commit_sha,
                skill.id,
                skill.commit_sha,
            )
            if skill.commit_sha is None:
                raise SkillNotReadyError(skill.id)
            commit_sha = skill.commit_sha
            skill_dir = self._skills_store.skill_dir(skill, commit_sha)
            if not skill_dir.exists():
                raise SkillNotReadyError(skill.id)

        agent = self._registry.get(
            workflow.agent_skill_id,
            commit_sha,
            skill_dir,
            tenant_id=workflow.tenant_id,
            kind=AgentKind.design,
        )
        return agent, workflow

    async def _adk_session(self, workflow: Workflow) -> Session | None:
        """Return the ADK session holding a workflow's design session chat.

        Keyed by the workflow's ``created_by``, not the current user, so every
        developer in the tenant reads and writes the one shared conversation
        rather than forking a private session of their own.

        Args:
            workflow: The workflow whose design chat to look up.

        Returns:
            The ADK session, or ``None`` when it does not exist yet (the
            background generation run has not started).
        """
        return await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, workflow.tenant_id),
            user_id=workflow.created_by,
            session_id=workflow.session_id,
        )

    async def get_messages(
        self, workflow_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a workflow's design session.

        The history is keyed by the session's owner (``created_by``), so every
        developer sees the one shared conversation. Each message carries the
        ``senderUserId`` recorded for it, letting the UI show who said what;
        agent messages and the unattended background generation run's messages
        have none and fall back in the UI. ``workflowTaskId`` is always ``None``
        here — a design session edits task *templates*, not the status-ful tasks
        a run works through — but is still emitted so the payload shape matches
        the workflow-execution messages endpoint and the frontend chat
        components can be reused unchanged. Returns an empty list when the ADK
        session does not exist yet.

        Args:
            workflow_id: Identifier of the workflow whose messages to fetch.
            caller: The authenticated user requesting the history.
            caller_roles: The caller's effective roles, including any inherited
                from their groups.

        Returns:
            The session's messages as plain JSON-serializable dicts.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForbiddenError: If the caller is neither a developer, a super admin,
                nor the workflow's creator.
        """
        workflow = await self.get_for_design(
            workflow_id, caller=caller, caller_roles=caller_roles
        )
        session = await self._adk_session(workflow)
        if session is None:
            return []
        meta = await self._meta.meta_for_session(
            MessageScope.design_session(workflow_id)
        )
        return session_attribution.merge_message_meta(
            adk_events_to_messages(session.events), meta
        )

    async def attributable_keys(self, workflow_id: str) -> set[str]:
        """Return the correlation keys of the design session's attributable events.

        Snapshotting this set before an agent run lets the router attribute
        whatever appears afterwards to the user who drove the run — see
        :func:`services.session_attribution.attributable_keys`. Returns an empty
        set when the ADK session does not exist yet (before the first run).

        Called only after :meth:`resolve_agent` has already authorized the
        caller, so it deliberately skips the design-access check.

        Args:
            workflow_id: Identifier of the workflow whose events to read.

        Returns:
            The set of correlation keys (event ids and tool_call_ids)
            representing attributable events already present in the design
            session.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
        """
        workflow = await self.get(workflow_id)
        return session_attribution.attributable_keys(await self._adk_session(workflow))

    async def record_new_senders(
        self, workflow_id: str, prior_keys: set[str], sender_user_id: str
    ) -> None:
        """Attribute the design session's new events to ``sender_user_id``.

        Everything the session gained since ``prior_keys`` was snapshotted was
        produced by the current user, so it is recorded against them — see
        :func:`services.session_attribution.record_new_senders` for the
        read-then-diff rules. Does nothing when the ADK session does not exist.

        Like :meth:`attributable_keys`, this runs after the caller was
        authorized by :meth:`resolve_agent`, so it skips the access check.

        Args:
            workflow_id: Identifier of the workflow that was run.
            prior_keys: The attributable keys present before the run.
            sender_user_id: The user who sent the new messages.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForeignKeyViolationError: If ``sender_user_id`` does not match a user.
        """
        workflow = await self.get(workflow_id)
        await session_attribution.record_new_senders(
            self._meta,
            MessageScope.design_session(workflow_id),
            await self._adk_session(workflow),
            prior_keys,
            sender_user_id,
        )

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        caller_roles: Collection[str],
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[Workflow]:
        """Return a page of Workflow records visible to the caller.

        A caller who is not a ``developer`` (or, via the ``super_admin``
        bypass, a ``super_admin``) never sees ``draft`` workflows: a matching
        ``status:ne:draft`` filter is appended to ``filters``, combining with
        (never widening) whatever the caller supplied -- mirrors
        ``UserService.list``'s tenant-scoping filter
        (``services/user.py``).

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            tag_ids: Narrows the page to workflows carrying every listed tag.

        Returns:
            The requested page of workflows.
        """
        if not has_any_role(caller_roles, Role.developer):
            filters = (
                *filters,
                FilterSpec(field="status", op="ne", value=WorkflowStatus.draft.value),
            )
        return await self._workflows.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, workflow: Workflow) -> WorkflowRead:
        """Project one Workflow into its API read view, attaching its tags.

        Args:
            workflow: The persisted workflow to project.

        Returns:
            The read view, with tag ids attached.
        """
        return await build_workflow_read(self._workflows, workflow)

    async def to_read_many(self, workflows: Sequence[Workflow]) -> _ReadList:
        """Project a page of Workflows into read views, reading their tags in one query.

        Args:
            workflows: The persisted records to project.

        Returns:
            The read views, in the order they were given.
        """
        by_id = await self._workflows.tag_ids_for_many([x.id for x in workflows])
        return [
            WorkflowRead.from_workflow(x, tag_ids=by_id.get(x.id, []))
            for x in workflows
        ]

    async def set_tags(self, workflow_id: str, tag_ids: Sequence[str]) -> Workflow:
        """Replace a Workflow's tag attachments wholesale.

        Args:
            workflow_id: Identifier of the workflow to retag.
            tag_ids: Ids of the tags it should carry.

        Returns:
            The workflow, unchanged apart from its attachments.

        Raises:
            NotFoundError: If no workflow exists with the given ID.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        return await self._workflows.set_tags(workflow_id, tag_ids)

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
            # Direct roles, not effective ones: this asks only about
            # ``super_admin``, which a user group can never grant.
            and not has_any_role(caller.roles, Role.super_admin)
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

    async def execute(
        self, workflow_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> WorkflowExecution:
        """Start a workflow run by creating a WorkflowExecution with its tasks.

        Resolves the workflow and its skill, records a new WorkflowExecution
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
            caller: The authenticated user starting the run.
            caller_roles: The caller's effective roles — direct grants plus
                everything inherited from their groups. A ``draft`` workflow is
                only runnable when they hold the ``developer`` role
                (``super_admin`` bypasses via
                :func:`~models.user.has_any_role`); ``published`` and
                ``modified`` workflows are runnable by any caller who reached
                this route (role-gated to ``requester``/``developer`` at the
                router).

        Returns:
            The created WorkflowExecution.

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
            workflow.status is WorkflowStatus.draft
            and has_any_role(caller_roles, Role.developer)
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

        execution_create = WorkflowExecutionCreate(
            session_id=session_id,
            name=self._generate_execution_name(name),
            description=description,
            agent_skill_id=skill.id,
            agent_skill_name=skill.name,
            agent_skill_repo_url=skill.repo_url,
            agent_skill_repo_path=skill.repo_path,
            agent_skill_commit_sha=skill.commit_sha,
            initiator_id=user,
        )
        execution = await self._execution_repo.create(
            execution_create, workflow_id=workflow.id, user_id=user
        )
        execution_id = execution.id

        # Copy the task templates in dependency order, remapping template ids to the
        # freshly created task ids so the edges land on the copies.
        template_to_task: dict[str, str] = {}
        for template in _topo_order(templates):
            task = await self._tasks.create(
                WorkflowTaskCreate(
                    workflow_execution_id=execution_id,
                    title=template.title,
                    description=template.description,
                    status=WorkflowTaskStatus.pending,
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
        # session expires the ``execution`` instance, and serializing an expired one
        # outside the request's greenlet context would fail.
        created = await self._execution_repo.get(execution_id)
        if created is None:  # pragma: no cover - just created above
            raise NotFoundError("WorkflowExecution", execution_id)
        return created

    def _generate_execution_name(self, name: str) -> str:
        """Build a WorkflowExecution name from the workflow name plus a random suffix.

        Appends a 6-character lowercase hex suffix so repeated runs of the same
        workflow stay distinguishable in the executions list; the timestamp
        itself is already available via ``createdAt``.

        Args:
            name: The workflow (or published snapshot) name to base the run's
                name on.

        Returns:
            The trimmed name followed by a ``-`` and a random hex suffix.
        """
        return f"{name.strip()}-{secrets.token_hex(3)}"

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
