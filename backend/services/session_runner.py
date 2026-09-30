"""The server side of a workflow session: runs the turns no browser is driving.

A run no longer depends on someone keeping its chat open. Its kickoff, and its
resumption once an approval is decided -- from the chat or from the approvals
list -- are queued on the session (:mod:`services.session_queue`) and run here,
in the API process, by one dispatcher per process.

Each turn runs under the session's run lock -- the same cross-process lock a
browser-driven turn takes -- tried without waiting: a session another replica
(or a browser) is already running is skipped, and a ``running`` session whose
lock turns out to be free belongs to a process that died mid-turn, and is
resumed with a prompt telling the agent so.

A server-driven turn acts as the run's initiator, whoever queued it. What it
adds to the chat is attributed to the input's sender -- the approver, for a
decision -- so the chat still shows who decided.
"""

import asyncio
import logging
import uuid

import anyio
from ag_ui.core import BaseEvent, Context, EventType, RunAgentInput, RunErrorEvent
from google.adk.sessions import BaseSessionService
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure import database
from infrastructure.agent import AgentRegistry, tenant_app_name, with_user_id
from infrastructure.client_tools import a2ui_context, client_tools
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from infrastructure.skill_manager import SkillManager
from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.workflow_execution import WorkflowExecution
from repositories.agent_skill import SqlAgentSkillRepository
from repositories.approval import SqlApprovalRepository
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.execution_session import SqlExecutionSessionRepository
from repositories.execution_session_queue import due_sessions
from repositories.mcp_server import SqlMCPServerRepository
from repositories.mcp_tool_invocation import SqlMcpToolInvocationRepository
from repositories.message_meta import SqlMessageMetaRepository
from repositories.user import SqlUserRepository
from repositories.user_group import SqlUserGroupRepository
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from repositories.workflow_task import SqlWorkflowTaskRepository
from services.approver_groups import ApproverGroupResolver
from services.session_file import build_session_file_store, describe_session_files
from services.session_inputs import SessionInput, WaitingCall, build_messages
from services.session_queue import settle_turn, wait_for_wake
from services.workflow_execution import WorkflowExecutionService
from services.workflow_execution_access import WorkflowExecutionAccessPolicy

logger = logging.getLogger(__name__)

#: How often the dispatcher looks for due sessions when nothing wakes it.
POLL_INTERVAL_SECONDS = 2.0

#: Stands in for the input of a ``running`` session whose turn was cut off.
_RECOVERY = SessionInput(kind="recovery")


class SessionRunner:
    """Runs one server-driven turn at a time for whichever session is due.

    Holds the process-wide collaborators a turn needs; the per-turn ones --
    repositories on a fresh database session, scoped to the session's tenant
    -- are built inside :meth:`run_turn`, since the runner works outside any
    request.
    """

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        skills_store: SkillManager,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        """Store the process-wide collaborators.

        Args:
            registry: Registry resolving each run's ADK agent.
            skills_store: Store locating a skill revision's directory.
            session_service: The ADK session store.
            app_name: Base ADK application name (see :func:`tenant_app_name`).
        """
        self._registry = registry
        self._skills_store = skills_store
        self._session_service = session_service
        self._app_name = app_name

    async def run_turn(self, session_id: str, tenant_id: str) -> None:
        """Run one turn for a due session, if nobody else is running it.

        Args:
            session_id: The ADK session to run.
            tenant_id: The tenant it belongs to.
        """
        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            executions = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
            sessions = SqlExecutionSessionRepository(db, tenant_id=tenant_id)
            row = await sessions.get(session_id)
            execution = await executions.get(row.workflow_execution_id) if row else None
            if row is None or execution is None:
                return
            key = agent_run_key(
                tenant_app_name(self._app_name, tenant_id),
                execution.initiator_id,
                session_id,
            )
            try:
                async with advisory_lock(key, wait_seconds=0):
                    await self._run_locked(db, tenant_id, session_id, execution)
            except LockNotAcquiredError:
                return

    async def _run_locked(
        self,
        db: AsyncSession,
        tenant_id: str,
        session_id: str,
        execution: WorkflowExecution,
    ) -> None:
        """The body of :meth:`run_turn`, once the session's run lock is held."""
        executions = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
        sessions = SqlExecutionSessionRepository(db, tenant_id=tenant_id)
        # Re-read under the lock: the row may have moved on since it was due.
        row = await sessions.get(session_id)
        if row is None or row.status not in (
            ExecutionSessionStatus.queued,
            ExecutionSessionStatus.running,
        ):
            return
        session_input = _input_of(row)
        waiting = [WaitingCall.model_validate(c) for c in row.waiting_on]
        initiator = execution.initiator_id
        await sessions.set_state(
            session_id, status=ExecutionSessionStatus.running, user_id=initiator
        )

        service = self._execution_service(db, tenant_id)
        try:
            agent = await service.agent_for(execution)
        except Exception:
            # Left ``running``, the session would be retried on every poll.
            logger.exception("cannot resolve the agent for session %s", session_id)
            await sessions.set_state(
                session_id,
                status=ExecutionSessionStatus.error,
                user_id=initiator,
                clear_input=True,
            )
            return
        input_data = with_user_id(
            RunAgentInput(
                thread_id=session_id,
                run_id=str(uuid.uuid4()),
                state={},
                messages=build_messages(waiting, session_input),
                tools=client_tools(),
                context=await self._context(db, tenant_id, execution),
                forwarded_props={},
            ),
            initiator,
            acting_user_id=initiator,
        )
        prior_keys = await service.attributable_keys(execution.id)
        events: list[BaseEvent] = []
        try:
            async for event in agent.run(input_data):
                events.append(event)
        finally:
            with anyio.CancelScope(shield=True):
                if session_input.sender_id is not None:
                    await service.record_new_senders(
                        execution.id, prior_keys, session_input.sender_id
                    )
                await service.record_message_tasks(execution.id)
                await settle_turn(
                    sessions=sessions,
                    approvals=self._approvals(db, tenant_id, executions),
                    executions=executions,
                    session_id=session_id,
                    execution_id=execution.id,
                    previous=waiting,
                    answered=[session_input.tool_call_id]
                    if session_input.tool_call_id
                    else [],
                    events=events,
                    failed=any(isinstance(e, RunErrorEvent) for e in events)
                    or not any(e.type == EventType.RUN_FINISHED for e in events),
                    user_id=initiator,
                )

    async def _context(
        self, db: AsyncSession, tenant_id: str, execution: WorkflowExecution
    ) -> list[Context]:
        """Build the turn's context the way the agent route does for a browser turn."""
        settings = get_settings()
        files = await build_session_file_store(
            db,
            tenant_id=tenant_id,
            max_file_bytes=settings.session_file_max_bytes,
            max_total_bytes=settings.session_files_max_total_bytes,
        ).list(execution.id)
        context: list[Context] = []
        if execution.description:
            context.append(
                Context(description="Workflow description", value=execution.description)
            )
        if files:
            context.append(
                Context(
                    description="Files attached to this session",
                    value=describe_session_files(files),
                )
            )
        return context + a2ui_context()

    def _approvals(
        self,
        db: AsyncSession,
        tenant_id: str,
        executions: SqlWorkflowExecutionRepository,
    ) -> SqlApprovalRepository:
        """Build an unrestricted approval repository on the turn's database session."""
        groups = SqlUserGroupRepository(db, SqlUserRepository(db), tenant_id=tenant_id)
        return SqlApprovalRepository(db, executions, groups, tenant_id=tenant_id)

    def _execution_service(
        self, db: AsyncSession, tenant_id: str
    ) -> WorkflowExecutionService:
        """Build the execution service on the turn's database session.

        Unrestricted by access-control tags, like every background job: the
        runner acts for the run itself. Its access policy is never consulted --
        the runner only resolves the agent and records attribution.
        """
        executions = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
        groups = SqlUserGroupRepository(db, SqlUserRepository(db), tenant_id=tenant_id)
        approvals = SqlApprovalRepository(db, executions, groups, tenant_id=tenant_id)
        return WorkflowExecutionService(
            executions,
            SqlWorkflowTaskRepository(
                db,
                executions,
                SqlMCPServerRepository(db, tenant_id=tenant_id),
                tenant_id=tenant_id,
            ),
            SqlMessageMetaRepository(db, tenant_id=tenant_id),
            SqlMcpToolInvocationRepository(db, tenant_id=tenant_id),
            SqlAgentSkillRepository(db, tenant_id=tenant_id),
            self._skills_store,
            self._registry,
            self._session_service,
            self._app_name,
            WorkflowExecutionAccessPolicy(
                approvals,
                ApproverGroupResolver(groups, SqlEffectiveRoleRepository(db)),
            ),
        )


def _input_of(row: ExecutionSession) -> SessionInput:
    """Return the input a due session's turn runs on.

    A ``running`` row is only due when the process running it died -- a live
    turn holds the lock -- so it is resumed with the recovery prompt, whatever
    input it was given.
    """
    if row.status is ExecutionSessionStatus.running or row.pending_input is None:
        return _RECOVERY
    return SessionInput.model_validate(row.pending_input)


async def run_session_dispatcher(runner: SessionRunner, *, concurrency: int) -> None:
    """Run due sessions' turns until cancelled, at most ``concurrency`` at once.

    Looks for due sessions whenever this process queues input and every
    :data:`POLL_INTERVAL_SECONDS` otherwise -- the poll is what picks up input
    queued on another replica, and sessions whose process died.

    Args:
        runner: The runner that executes each turn.
        concurrency: Most turns this process runs at once.
    """
    slots = asyncio.Semaphore(concurrency)
    in_flight: set[str] = set()
    tasks: set[asyncio.Task[None]] = set()

    async def _one(session_id: str, tenant_id: str) -> None:
        try:
            await runner.run_turn(session_id, tenant_id)
        except Exception:
            logger.exception("session turn failed for session %s", session_id)
        finally:
            in_flight.discard(session_id)
            slots.release()

    try:
        while True:
            try:
                async with AsyncSession(database.engine) as db:
                    due = await due_sessions(db)
            except Exception:
                logger.exception("could not look for due sessions")
                due = []
            for session_id, tenant_id in due:
                if session_id in in_flight:
                    continue
                if slots.locked():
                    break
                await slots.acquire()
                in_flight.add(session_id)
                task = asyncio.create_task(_one(session_id, tenant_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await wait_for_wake(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
