"""Use case service for WorkflowExecution resources.

Exposes WorkflowExecution reads, the parent-checked task listing, and resolution
of the ADK agent driving an execution's workflow session. HTTP concerns (SSE encoding, streaming,
message filtering) remain in the router; this service only owns the data access
and agent-resolution business rules.
"""

import builtins
import logging
from collections.abc import Collection, Sequence

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.sessions import BaseSessionService, Session

from infrastructure.agent import AgentKind, AgentRegistry, tenant_app_name
from infrastructure.client_tools import RENDER_A2UI_TOOL_NAME
from infrastructure.skill_manager import SkillManager
from models.execution_session import (
    ExecutionSession,
    ExecutionSessionStatus,
    SessionHistory,
    SessionInputCreate,
)
from models.mcp_tool_invocation import MCPToolInvocation
from models.message_meta import MessageScope
from models.user import Role, User, has_any_role
from models.workflow_execution import WorkflowExecution, WorkflowExecutionRead
from models.workflow_task import WorkflowTaskRead
from repositories.agent_skill import AgentSkillRepository
from repositories.exceptions import (
    ForbiddenError,
    NotFoundError,
    SessionAwaitingApprovalError,
    SessionInputValidationError,
    SessionRunInProgressError,
    SkillNotReadyError,
)
from repositories.execution_session import ExecutionSessionRepository
from repositories.mcp_tool_invocation import McpToolInvocationRepository
from repositories.message_meta import MessageMetaRepository
from repositories.query import FilterSpec, SortSpec
from repositories.session_stream import SessionStreamRepository
from repositories.workflow_execution import WorkflowExecutionRepository
from repositories.workflow_task import WorkflowTaskRepository
from services import session_attribution
from services.session_inputs import SessionInput, WaitingCall
from services.session_queue import queue_input
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
        sessions: ExecutionSessionRepository,
        stream: SessionStreamRepository,
    ) -> None:
        """Initialize the service.

        Args:
            execution_repo: Repository providing WorkflowExecution persistence,
                restricted to the runs the caller's access-control tags admit
                (see :mod:`models.tag`). Every method here fetches through it
                first, so a run that copied an access-control tag from its
                workflow (see :meth:`services.workflow.WorkflowService.execute`)
                reads as 404 to a caller whose groups no longer carry it --
                even as the run's own initiator or a designated approver, and
                whether they are browsing it, reading its tasks, or driving
                its agent -- before the participant-based ``access`` policy
                below ever runs.
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
            sessions: Repository holding the run's ADK sessions, which input
                is queued on.
            stream: The sessions' streamed events, read for the cursor a
                history comes with.
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
        self._sessions = sessions
        self._stream = stream

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
            NotFoundError: If no execution exists with the given ID, or it is
                hidden by an access-control tag the caller's groups do not hold.
        """
        execution = await self._execution_repo.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        return execution

    async def _get_authorized(
        self, execution_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> WorkflowExecution:
        """Fetch a WorkflowExecution and authorize the caller for read access.

        The fetch-then-authorize step shared by every read-only method below,
        factored out so each one pays for exactly the data it needs — unlike
        :meth:`get`, this returns the raw entity rather than the tag-ids
        projection, since most callers here use it only for the existence and
        access checks (see :meth:`list_tasks`, :meth:`list_tool_invocations`)
        or need the raw entity for further work (see :meth:`get_messages`).

        Args:
            execution_id: Identifier of the execution to fetch.
            caller: The authenticated user requesting access.
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

    async def get(
        self, execution_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> WorkflowExecutionRead:
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
            The matching execution, with its tag ids attached.

        Raises:
            NotFoundError: If no execution exists with the given ID, or it is
                hidden by an access-control tag the caller's groups do not hold.
            ForbiddenError: If the caller is neither the execution initiator,
                a designated approver of the execution, nor holds ``admin``
                or ``super_admin``.
        """
        execution = await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
        tag_ids = await self._execution_repo.tag_ids_for(execution_id)
        return WorkflowExecutionRead.from_execution(execution, tag_ids=tag_ids)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        caller: User,
        caller_roles: Collection[str],
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowExecutionRead]:
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
            The requested page of executions, newest first by default, each
            with its tag ids attached. Excludes, in addition to the
            participant filter above, any execution gated by an
            access-control tag the caller's groups do not hold -- see
            :attr:`_execution_repo`.
        """
        if has_any_role(caller_roles, Role.super_admin, Role.admin):
            visible_to_user_id: str | None = None
            visible_to_group_ids: tuple[str, ...] = ()
        else:
            visible_to_user_id = caller.id
            visible_to_group_ids = await self._access.approver_group_ids(
                caller, caller_roles
            )
        executions = await self._execution_repo.list(
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
            visible_to_user_id=visible_to_user_id,
            visible_to_group_ids=visible_to_group_ids,
        )
        tags_by_execution = await self._execution_repo.tag_ids_for_many(
            [e.id for e in executions]
        )
        return [
            WorkflowExecutionRead.from_execution(
                e, tag_ids=tags_by_execution.get(e.id, [])
            )
            for e in executions
        ]

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
        await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
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
        await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
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
        return await self.agent_for(execution), execution

    async def agent_for(self, execution: WorkflowExecution) -> ADKAgent:
        """Return the ADK agent for an execution's skill revision, without authorizing anyone.

        The body of :meth:`resolve_agent` minus its access check, for the
        session runner (:mod:`services.session_runner`), which drives turns on
        the run's own behalf rather than for a caller.

        Args:
            execution: The execution whose agent to resolve.

        Returns:
            The ADK agent configured for the execution's skill revision.

        Raises:
            SkillNotReadyError: If neither the revision the execution pinned nor
                the skill's current revision is present in the store.
        """
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

        return self._registry.get(
            execution.agent_skill_id,
            commit_sha,
            skill_dir,
            tenant_id=execution.tenant_id,
            kind=AgentKind.execution,
        )

    async def list_sessions(
        self, execution_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> builtins.list[ExecutionSession]:
        """Return the ADK sessions of a run, main session first.

        Read access, like the chat itself.

        Args:
            execution_id: Identifier of the WorkflowExecution.
            caller: The authenticated user.
            caller_roles: The caller's effective roles.

        Returns:
            The run's sessions with their status and what they wait on.

        Raises:
            NotFoundError: If the execution does not exist or is hidden.
            ForbiddenError: If the caller may not read the execution.
        """
        await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
        return await self._sessions.list_for_execution(execution_id)

    async def get_session_messages(
        self,
        execution_id: str,
        session_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
    ) -> SessionHistory:
        """Return one session's chat history and the cursor to stream it from.

        The ADK session is keyed by the run's initiator, so every authorized
        viewer -- a designated approver included -- reads the one shared
        conversation. While a turn is under way, the history stops where that
        turn began and the cursor points at the turn's first streamed event: a
        viewer joining mid-turn gets the turn from the stream, once, instead of
        half of it twice. The cursor is read before the history, so an event
        written in between is streamed rather than lost.

        Args:
            execution_id: Identifier of the WorkflowExecution.
            session_id: The ADK session to read.
            caller: The authenticated user requesting the history.
            caller_roles: The caller's effective roles.

        Returns:
            The messages, with sender and task attribution merged in, and the
            stream cursor.

        Raises:
            NotFoundError: If the execution or the session does not exist, the
                session belongs to another run, or the execution is hidden.
            ForbiddenError: If the caller may not read the execution.
        """
        execution = await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
        row = await self._session_of(execution_id, session_id)
        cursor = await self._stream.cursor_before_run(session_id, row.active_run_id)
        session = await self._adk_session(execution, session_id)
        if session is None:
            return SessionHistory(messages=[], stream_cursor=cursor)
        end = row.run_event_index if row.active_run_id is not None else None
        # A branch's leading events are its parent's history, copied when it
        # forked; its own chat starts after them.
        events = session.events[row.fork_event_count : end]
        meta = await self._meta.meta_for_session(
            MessageScope.workflow_session(execution_id)
        )
        return SessionHistory(
            messages=session_attribution.merge_message_meta(
                adk_events_to_messages(events), meta
            ),
            stream_cursor=cursor,
        )

    async def authorize_stream(
        self,
        execution_id: str,
        session_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
    ) -> None:
        """Check the caller may watch a session's stream, before it is opened.

        Read access, like the history: a plain admin may watch a run without
        being able to drive it.

        Raises:
            NotFoundError: If the execution or the session does not exist.
            ForbiddenError: If the caller may not read the execution.
        """
        await self._get_authorized(
            execution_id, caller=caller, caller_roles=caller_roles
        )
        await self._session_of(execution_id, session_id)

    async def send_input(
        self,
        execution_id: str,
        session_id: str,
        data: SessionInputCreate,
        *,
        caller: User,
    ) -> ExecutionSession:
        """Queue a person's input for a session's next turn, which the server runs.

        Driving the chat is an action, so it takes ``assert_access`` (the
        initiator, a designated approver, or a super admin) rather than read
        access. Answering a form the agent rendered is narrower still -- the
        initiator only, like submitting it ever was. The turn runs with the
        sender's own authority.

        Args:
            execution_id: Identifier of the WorkflowExecution.
            session_id: The ADK session to send to.
            data: A chat message, or the answer to a form the session waits on.
            caller: The authenticated user sending it.

        Returns:
            The session, now ``queued``.

        Raises:
            NotFoundError: If the execution or the session does not exist.
            ForbiddenError: If the caller may not drive the run, or answers a
                form without being its initiator.
            SessionInputValidationError: If the input is empty, answers a call
                the session is not waiting on, or targets a finished branch.
            SessionAwaitingApprovalError: If a message is sent while the
                session waits on an approval.
            SessionRunInProgressError: If the session already has a turn queued
                or running.
        """
        execution = await self._get(execution_id)
        await self._access.assert_access(execution_id, execution.initiator_id, caller)
        row = await self._session_of(execution_id, session_id)
        if row.parent_id is not None and row.status is ExecutionSessionStatus.done:
            raise SessionInputValidationError("this branch session has finished")
        waiting = [WaitingCall.model_validate(c) for c in row.waiting_on]
        if data.a2ui_action is not None:
            if caller.id != execution.initiator_id:
                raise ForbiddenError("only the run's initiator can answer its forms")
            if not any(
                c.tool_call_id == data.a2ui_action.tool_call_id
                and c.name == RENDER_A2UI_TOOL_NAME
                for c in waiting
            ):
                raise SessionInputValidationError(
                    "the session is not waiting on that form"
                )
            session_input = SessionInput(
                kind="tool_result",
                tool_call_id=data.a2ui_action.tool_call_id,
                content=data.a2ui_action.content,
                sender_id=caller.id,
                acting_user_id=caller.id,
            )
        else:
            text = (data.message or "").strip()
            if not text:
                raise SessionInputValidationError("the message is empty")
            if row.status is ExecutionSessionStatus.waiting_for_approval:
                raise SessionAwaitingApprovalError(session_id)
            session_input = SessionInput(
                kind="message", text=text, sender_id=caller.id, acting_user_id=caller.id
            )
        if not await queue_input(
            self._sessions, session_id, session_input, user_id=caller.id
        ):
            raise SessionRunInProgressError(session_id)
        return await self._session_of(execution_id, session_id)

    async def _session_of(self, execution_id: str, session_id: str) -> ExecutionSession:
        """Return a session of the execution ``execution_id``, or raise NotFoundError.

        Takes the id rather than the execution itself: a commit since it was
        read (queueing input commits) leaves the ORM object expired, and
        reading it again would need a lazy load outside the request's greenlet.
        """
        row = await self._sessions.get(session_id)
        if row is None or row.workflow_execution_id != execution_id:
            raise NotFoundError("ExecutionSession", session_id)
        return row

    async def _adk_session(
        self, execution: WorkflowExecution, session_id: str | None = None
    ) -> Session | None:
        """Return the ADK session holding one of an execution's chats.

        Keyed by the execution's initiator, not the current user, so every
        authorized viewer (for example a designated approver) reads the one
        shared conversation.

        Args:
            execution: The WorkflowExecution whose chat to look up.
            session_id: The session to read; the main session when omitted.

        Returns:
            The ADK session, or ``None`` when it does not exist yet (before the
            first turn).
        """
        return await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, execution.tenant_id),
            user_id=execution.initiator_id,
            session_id=session_id or execution.session_id,
        )

    async def attributable_keys(
        self, execution_id: str, session_id: str | None = None
    ) -> set[str]:
        """Return the correlation keys of the workflow session's attributable events.

        Snapshotting this set before an agent run lets the router attribute
        whatever appears afterwards to the user who drove the run — see
        :func:`services.session_attribution.attributable_keys`. Returns an empty
        set when the ADK session does not exist yet (before the first run).

        Args:
            execution_id: Identifier of the WorkflowExecution whose events to read.
            session_id: The session to read; the main session when omitted.

        Returns:
            The set of correlation keys (event ids and tool_call_ids)
            representing attributable events already present in the workflow
            session.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
        """
        execution = await self._get(execution_id)
        return session_attribution.attributable_keys(
            await self._adk_session(execution, session_id)
        )

    async def record_new_senders(
        self,
        execution_id: str,
        prior_keys: set[str],
        sender_user_id: str,
        *,
        session_id: str | None = None,
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
            session_id: The session the run was in; the main session when
                omitted. Attribution rows are keyed by event id, which is
                unique across the run's sessions.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
            ForeignKeyViolationError: If ``sender_user_id`` does not match a user.
        """
        execution = await self._get(execution_id)
        await session_attribution.record_new_senders(
            self._meta,
            MessageScope.workflow_session(execution_id),
            await self._adk_session(execution, session_id),
            prior_keys,
            sender_user_id,
        )

    async def record_message_tasks(
        self, execution_id: str, *, session_id: str | None = None, start: int = 0
    ) -> None:
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
            session_id: The session the run was in; the main session when
                omitted.
            start: How many leading events to skip -- a branch session's
                copy of its parent's history, already associated there.

        Raises:
            NotFoundError: If no WorkflowExecution exists with the given ID.
        """
        execution = await self._get(execution_id)
        session = await self._adk_session(execution, session_id)
        if session is None:
            return
        # Capture the audit user before the loop: each set_task commit expires
        # the ``execution`` instance, and re-reading ``execution.created_by`` afterwards would
        # trigger a lazy load outside the async greenlet context.
        owner_id = execution.created_by
        current_task_id: str | None = None
        for event in session.events[start:]:
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
