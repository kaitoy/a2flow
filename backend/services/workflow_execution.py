"""Use case service for WorkflowExecution resources.

Exposes WorkflowExecution reads, the parent-checked task listing, and resolution
of the ADK agent driving an execution's workflow session. HTTP concerns (SSE encoding, streaming,
message filtering) remain in the router; this service only owns the data access
and agent-resolution business rules.
"""

import builtins
import logging
from collections.abc import Collection, Sequence
from typing import Any

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.sessions import BaseSessionService, Session

from infrastructure.agent import AgentKind, AgentRegistry, tenant_app_name
from infrastructure.skill_manager import SkillManager
from models.mcp_tool_invocation import MCPToolInvocation
from models.message_meta import MessageScope
from models.user import Role, User, has_any_role
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTaskRead
from repositories import (
    AgentSkillRepository,
    McpToolInvocationRepository,
    MessageMetaRepository,
    WorkflowExecutionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import NotFoundError, SkillNotReadyError
from repositories.query import FilterSpec, SortSpec
from services import session_attribution
from services.workflow_execution_access import WorkflowExecutionAccessPolicy

logger = logging.getLogger(__name__)


class WorkflowExecutionService:
    """Application service orchestrating WorkflowExecution operations."""

    def __init__(
        self,
        execution_repo: WorkflowExecutionRepository,
        tasks: WorkflowTaskRepository,
        meta: MessageMetaRepository,
        invocations: McpToolInvocationRepository,
        skills: AgentSkillRepository,
        skills_store: SkillManager,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
        access: WorkflowExecutionAccessPolicy,
    ) -> None:
        """Initialize the service.

        Args:
            execution_repo: Repository providing WorkflowExecution persistence.
            tasks: Repository providing WorkflowTask persistence.
            meta: Repository recording and reading per-message side-channel
                metadata (sender attribution and task association) for the
                shared workflow session.
            invocations: Append-only audit of the MCP tool calls the proxy
                decided on, read back for the execution's tool-invocation list.
            skills: Repository providing AgentSkill persistence, read to resolve
                the ``repo_path`` and fallback revision of an execution's skill.
            skills_store: Store locating a skill revision's directory on disk.
            registry: Registry resolving ADK agents per skill revision.
            session_service: ADK session store, used to delete the workflow
                session when a WorkflowExecution is removed.
            app_name: ADK application name keying sessions in the store.
            access: Policy restricting execution-scoped operations to the
                initiator, the execution's designated approvers, admins
                (read-only), and super admins.
        """
        self._execution_repo = execution_repo
        self._tasks = tasks
        self._meta = meta
        self._invocations = invocations
        self._skills = skills
        self._skills_store = skills_store
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name
        self._access = access

    async def _get(self, execution_id: str) -> WorkflowExecution:
        """Return the WorkflowExecution with the given ID, without authorization.

        Used internally by run-completion bookkeeping (which executes after
        the caller was already authorized by :meth:`resolve_agent`) and as the
        fetch step of the authorized public methods — the missing-execution case
        must surface as 404 before any 403.

        Args:
            execution_id: Identifier of the execution to fetch.

        Returns:
            The matching WorkflowExecution.

        Raises:
            NotFoundError: If no execution exists with the given ID.
        """
        execution = await self._execution_repo.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        return execution

    async def get(
        self, execution_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> WorkflowExecution:
        """Return the WorkflowExecution with the given ID, authorizing the caller.

        Read-only: also passes a plain ``admin`` in the caller's tenant. Do
        not use this to authorize driving the execution's agent — see
        :meth:`resolve_agent`, which stays on the stricter participant-only
        check.

        Args:
            execution_id: Identifier of the execution to fetch.
            caller: The authenticated user requesting the execution.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.

        Returns:
            The matching WorkflowExecution.

        Raises:
            NotFoundError: If no execution exists with the given ID.
            ForbiddenError: If the caller is neither the execution initiator,
                a designated approver of the execution, nor holds ``admin``
                or ``super_admin``.
        """
        execution = await self._get(execution_id)
        await self._access.assert_read_access(
            execution_id, execution.initiator_id, caller, caller_roles
        )
        return execution

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        caller: User,
        caller_roles: Collection[str],
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowExecution]:
        """Return a page of WorkflowExecution records visible to the caller.

        A super admin or admin sees every execution in the tenant; anyone
        else sees only executions they initiated or are a designated approver
        of (any approval status) -- either named directly on an approval, or a
        member of a group one is addressed to, holding the ``approver`` role.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            caller: The authenticated user requesting the list.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of executions, newest first by default.
        """
        if has_any_role(caller_roles, Role.super_admin, Role.admin):
            visible_to_user_id: str | None = None
            visible_to_group_ids: tuple[str, ...] = ()
        else:
            visible_to_user_id = caller.id
            visible_to_group_ids = await self._access.approver_group_ids(
                caller, caller_roles
            )
        return await self._execution_repo.list(
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
            visible_to_user_id=visible_to_user_id,
            visible_to_group_ids=visible_to_group_ids,
        )

    async def list_tasks(
        self,
        execution_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowTaskRead]:
        """Return the WorkflowTasks belonging to an execution.

        Args:
            execution_id: Identifier of the parent execution.
            caller: The authenticated user requesting the tasks.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of tasks for the execution.

        Raises:
            NotFoundError: If the parent execution does not exist, so callers
                can distinguish "no such execution" from "execution has no
                tasks".
            ForbiddenError: If the caller is neither the execution initiator,
                a designated approver of the execution, nor holds ``admin``
                or ``super_admin``.
        """
        await self.get(execution_id, caller=caller, caller_roles=caller_roles)
        return await self._tasks.list(
            limit=limit,
            offset=offset,
            workflow_execution_id=execution_id,
            sort=sort,
            filters=filters,
        )

    async def list_tool_invocations(
        self,
        execution_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[MCPToolInvocation]:
        """Return the MCP tool-call decisions recorded for an execution.

        These are the calls that actually reached
        :class:`infrastructure.mcp_gateway.McpGateway` — allowed ones that went
        upstream and denied ones that a policy vetoed. A call answered by a mock
        (see :mod:`infrastructure.tool_mocks`) never reaches the proxy and so is
        deliberately absent here; the chat transcript is where a mocked call is
        inspected.

        Args:
            execution_id: Identifier of the parent execution.
            caller: The authenticated user requesting the records.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of recorded decisions, newest first by default.

        Raises:
            NotFoundError: If the parent execution does not exist.
            ForbiddenError: If the caller is neither the execution initiator,
                a designated approver of the execution, nor holds ``admin``
                or ``super_admin``.
        """
        await self.get(execution_id, caller=caller, caller_roles=caller_roles)
        return await self._invocations.list_for_execution(
            execution_id, limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def resolve_agent(
        self, execution_id: str, *, caller: User
    ) -> tuple[ADKAgent, WorkflowExecution]:
        """Resolve the ADK agent driving an execution and the execution record.

        The skill revision comes from the execution record, so the run loads the
        code it started against no matter which replica serves it and no matter
        how many times the skill has been pulled since. Revision directories are
        immutable and live in the shared skill store, so this needs no lock and
        no clone — it only resolves a path that a pull can add siblings to but
        never rewrite.

        The record is returned alongside the agent so the caller can key the ADK
        run by the execution's initiator (``WorkflowExecution.initiator_id``)
        rather than the current user, letting every authorized viewer (for
        example a designated approver) share the one workflow session.

        Deliberately does not go through :meth:`get`: driving the agent is an
        action, not a read, so a plain ``admin`` who is neither the initiator
        nor a designated approver must not be able to trigger a run merely by
        being able to view it — see ``WorkflowExecutionAccessPolicy.assert_access``.

        Args:
            execution_id: Identifier of the execution whose agent to resolve.
            caller: The authenticated user driving the agent run.

        Returns:
            A ``(agent, workflow_execution)`` tuple: the ADK agent configured
            for the execution's skill revision, and the WorkflowExecution record
            itself.

        Raises:
            NotFoundError: If no execution exists with the given ID.
            ForbiddenError: If the caller is neither the execution initiator, a
                designated approver of the execution, nor a super admin. A
                plain ``admin`` who is none of those is rejected too.
            SkillNotReadyError: If neither the revision the execution pinned nor
                the skill's current revision is present in the store — the skill
                has never been cloned, or its store was wiped. An admin fixes it
                by pulling the skill.
        """
        execution = await self._get(execution_id)
        await self._access.assert_access(execution_id, execution.initiator_id, caller)
        skill = await self._skills.get(execution.agent_skill_id)
        if skill is None:
            raise SkillNotReadyError(execution.agent_skill_id)

        # Executions created before the store was revisioned pinned no revision;
        # they get the skill's current one.
        commit_sha = execution.agent_skill_commit_sha or skill.commit_sha
        if commit_sha is None:
            raise SkillNotReadyError(skill.id)

        skill_dir = self._skills_store.skill_dir(skill, commit_sha)
        if not skill_dir.exists():
            # The pinned revision is gone (a wiped volume, or a prune that
            # outran an execution's insert). The skill's current revision is
            # the only code left to run, so fall back to it rather than
            # stranding the conversation -- loudly, because it is not the code
            # the execution started with.
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
            execution.agent_skill_id,
            commit_sha,
            skill_dir,
            tenant_id=execution.tenant_id,
            kind=AgentKind.execution,
        )
        return agent, execution

    async def get_messages(
        self, execution_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a WorkflowExecution's workflow session.

        The ADK session is looked up by the WorkflowExecution's initiator
        (``execution.initiator_id``), so the same history is returned
        regardless of which authorized user requests it — a designated
        approver opening the chat sees the initiator's conversation instead
        of starting a fresh one.
        Returns an empty list when the ADK session does not exist yet (before
        the first agent run).

        Args:
            execution_id: Identifier of the WorkflowExecution whose messages to fetch.
            caller: The authenticated user requesting the history.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.

        Returns:
            The workflow session's messages as plain JSON-serializable dicts
            (the same shape as ``GET /sessions/{id}/messages``).

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
            ForbiddenError: If the caller is neither the execution initiator,
                a designated approver of the execution, nor holds ``admin``
                or ``super_admin``.
        """
        execution = await self.get(
            execution_id, caller=caller, caller_roles=caller_roles
        )
        session = await self._adk_session(execution)
        if session is None:
            return []
        meta = await self._meta.meta_for_session(
            MessageScope.workflow_session(execution_id)
        )
        return session_attribution.merge_message_meta(
            adk_events_to_messages(session.events), meta
        )

    async def _adk_session(self, execution: WorkflowExecution) -> Session | None:
        """Return the ADK session holding an execution's workflow session chat.

        Keyed by the execution's initiator, not the current user, so every
        authorized viewer (for example a designated approver) reads and writes
        the one shared conversation.

        Args:
            execution: The WorkflowExecution whose chat to look up.

        Returns:
            The ADK session, or ``None`` when it does not exist yet (before the
            first agent run).
        """
        return await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, execution.tenant_id),
            user_id=execution.initiator_id,
            session_id=execution.session_id,
        )

    async def attributable_keys(self, execution_id: str) -> set[str]:
        """Return the correlation keys of the workflow session's attributable events.

        Snapshotting this set before an agent run lets the router attribute
        whatever appears afterwards to the user who drove the run — see
        :func:`services.session_attribution.attributable_keys`. Returns an empty
        set when the ADK session does not exist yet (before the first run).

        Args:
            execution_id: Identifier of the WorkflowExecution whose events to read.

        Returns:
            The set of correlation keys (event ids and tool_call_ids)
            representing attributable events already present in the workflow
            session.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
        """
        execution = await self._get(execution_id)
        return session_attribution.attributable_keys(await self._adk_session(execution))

    async def record_new_senders(
        self, execution_id: str, prior_keys: set[str], sender_user_id: str
    ) -> None:
        """Attribute the workflow session's new events to ``sender_user_id``.

        Everything the session gained since ``prior_keys`` was snapshotted was
        produced by the current user, so it is recorded against them — see
        :func:`services.session_attribution.record_new_senders` for the
        read-then-diff rules. Does nothing when the ADK session does not exist.

        Args:
            execution_id: Identifier of the WorkflowExecution that was run.
            prior_keys: The attributable keys present before the run.
            sender_user_id: The user who sent the new messages.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
            ForeignKeyViolationError: If ``sender_user_id`` does not match a user.
        """
        execution = await self._get(execution_id)
        await session_attribution.record_new_senders(
            self._meta,
            MessageScope.workflow_session(execution_id),
            await self._adk_session(execution),
            prior_keys,
            sender_user_id,
        )

    async def record_message_tasks(self, execution_id: str) -> None:
        """Associate each ADK event with the WorkflowTask in progress at the time.

        The agent drives the task lifecycle by calling ``update_workflow_task``
        with ``status="in_progress"`` before working on a task. Walking the
        workflow session's events in order and tracking the most recent such
        transition therefore yields, for every event, the task that was in progress when it
        was produced. Each event from the first ``in_progress`` transition onward
        is recorded against its task (idempotently); events before any
        transition (the initial design exchange) are left unassociated.
        Non-``in_progress`` transitions (e.g. ``completed``) do not change the
        current task, so a task's own wrap-up stays grouped under it. Does
        nothing when the ADK session does not exist.

        Args:
            execution_id: Identifier of the WorkflowExecution that was run.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
        """
        execution = await self._get(execution_id)
        session = await self._adk_session(execution)
        if session is None:
            return
        # Capture the audit user before the loop: each set_task commit expires
        # the ``execution`` instance, and re-reading ``execution.created_by`` afterwards would
        # trigger a lazy load outside the async greenlet context.
        owner_id = execution.created_by
        current_task_id: str | None = None
        for event in session.events:
            for call in event.get_function_calls():
                if call.name != "update_workflow_task":
                    continue
                args = call.args or {}
                if args.get("status") == "in_progress":
                    task_id = args.get("task_id")
                    if isinstance(task_id, str) and task_id:
                        current_task_id = task_id
            if current_task_id is not None:
                await self._meta.set_task(
                    workflow_execution_id=execution_id,
                    adk_event_id=event.id,
                    workflow_task_id=current_task_id,
                    user_id=owner_id,
                )

    async def delete(self, execution_id: str) -> None:
        """Delete a WorkflowExecution and its workflow session.

        Authorization (admin or super admin) is enforced by the router's
        ``require_roles(Role.admin)`` route dependency, so this method does no
        access check of its own.

        Removes, in order: the ADK session keyed by the record's
        ``session_id`` (best effort — skipped if it no longer exists), then the
        WorkflowExecution row itself. Deleting the row cascades to its
        WorkflowTasks (and their dependency edges and tool bindings) via the
        ``ON DELETE CASCADE`` foreign keys.

        Args:
            execution_id: Identifier of the execution to delete.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
        """
        execution = await self._get(execution_id)
        scoped_app_name = tenant_app_name(self._app_name, execution.tenant_id)
        existing = await self._session_service.get_session(
            app_name=scoped_app_name,
            user_id=execution.initiator_id,
            session_id=execution.session_id,
        )
        if existing is not None:
            await self._session_service.delete_session(
                app_name=scoped_app_name,
                user_id=execution.initiator_id,
                session_id=execution.session_id,
            )
        await self._execution_repo.delete(execution_id)
