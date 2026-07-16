"""Use case service for WorkflowSession resources.

Exposes WorkflowSession reads, the parent-checked task listing, and resolution
of the ADK agent bound to a session. HTTP concerns (SSE encoding, streaming,
message filtering) remain in the router; this service only owns the data access
and agent-resolution business rules.
"""

import builtins
import logging
from collections.abc import Sequence
from typing import Any

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.sessions import BaseSessionService

from infrastructure.agent import AgentKind, AgentRegistry
from infrastructure.skill_manager import SkillManager
from models.user import User
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTaskRead
from repositories import (
    AgentSkillRepository,
    MessageMetaRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import NotFoundError, SkillNotReadyError
from repositories.query import FilterSpec, SortSpec
from services.workflow_session_access import WorkflowSessionAccessPolicy

logger = logging.getLogger(__name__)

#: Tool-response payload of the frontend's no-op ``render_a2ui``
#: acknowledgement (``RENDER_ACK_CONTENT`` in ``frontend/src/lib/a2uiAction.ts``,
#: mirroring the ``@ag-ui/a2ui-middleware`` convention). Such a response merely
#: unblocks the long-running render call for a surface nobody acted on, so it
#: must not be attributed to the user whose run happened to flush it.
_RENDER_ACK_RESPONSE = {"status": "rendered"}


class WorkflowSessionService:
    """Application service orchestrating WorkflowSession operations."""

    def __init__(
        self,
        ws_repo: WorkflowSessionRepository,
        tasks: WorkflowTaskRepository,
        meta: MessageMetaRepository,
        skills: AgentSkillRepository,
        skills_store: SkillManager,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
        access: WorkflowSessionAccessPolicy,
    ) -> None:
        """Initialize the service.

        Args:
            ws_repo: Repository providing WorkflowSession persistence.
            tasks: Repository providing WorkflowTask persistence.
            meta: Repository recording and reading per-message side-channel
                metadata (sender attribution and task association) for the
                shared workflow chat.
            skills: Repository providing AgentSkill persistence, read to resolve
                the ``repo_path`` and fallback revision of a session's skill.
            skills_store: Store locating a skill revision's directory on disk.
            registry: Registry resolving ADK agents per skill revision.
            session_service: ADK session store, used to delete the underlying
                chat session when a WorkflowSession is removed.
            app_name: ADK application name keying sessions in the store.
            access: Policy restricting session-scoped operations to the owner,
                the session's designated approvers, and super admins.
        """
        self._ws_repo = ws_repo
        self._tasks = tasks
        self._meta = meta
        self._skills = skills
        self._skills_store = skills_store
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name
        self._access = access

    async def _get(self, ws_id: str) -> WorkflowSession:
        """Return the WorkflowSession with the given ID, without authorization.

        Used internally by run-completion bookkeeping (which executes after
        the caller was already authorized by :meth:`resolve_agent`) and as the
        fetch step of the authorized public methods — the missing-session case
        must surface as 404 before any 403.

        Args:
            ws_id: Identifier of the session to fetch.

        Returns:
            The matching WorkflowSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ws = await self._ws_repo.get(ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        return ws

    async def get(self, ws_id: str, *, caller: User) -> WorkflowSession:
        """Return the WorkflowSession with the given ID, authorizing the caller.

        Args:
            ws_id: Identifier of the session to fetch.
            caller: The authenticated user requesting the session.

        Returns:
            The matching WorkflowSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner, a
                designated approver of the session, nor a super admin.
        """
        ws = await self._get(ws_id)
        await self._access.assert_access(ws_id, ws.user_id, caller)
        return ws

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowSession]:
        """Return a page of WorkflowSession records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of sessions, newest first by default.
        """
        return await self._ws_repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def list_tasks(
        self,
        ws_id: str,
        *,
        caller: User,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowTaskRead]:
        """Return the WorkflowTasks belonging to a session.

        Args:
            ws_id: Identifier of the parent session.
            caller: The authenticated user requesting the tasks.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of tasks for the session.

        Raises:
            NotFoundError: If the parent session does not exist, so callers can
                distinguish "no such session" from "session has no tasks".
            ForbiddenError: If the caller is neither the session owner, a
                designated approver of the session, nor a super admin.
        """
        await self.get(ws_id, caller=caller)
        return await self._tasks.list(
            limit=limit,
            offset=offset,
            workflow_session_id=ws_id,
            sort=sort,
            filters=filters,
        )

    async def resolve_agent(
        self, ws_id: str, *, caller: User
    ) -> tuple[ADKAgent, WorkflowSession]:
        """Resolve the ADK agent bound to a WorkflowSession and the session record.

        The skill revision comes from the session record, so the run loads the
        code it started against no matter which replica serves it and no matter
        how many times the skill has been pulled since. Revision directories are
        immutable and live in the shared skill store, so this needs no lock and
        no clone — it only resolves a path that a pull can add siblings to but
        never rewrite.

        The record is returned alongside the agent so the caller can key the ADK
        run by the session's owner (``WorkflowSession.user_id``) rather than the
        current user, letting every authorized viewer (for example a designated
        approver) share the same ADK session.

        Args:
            ws_id: Identifier of the session whose agent to resolve.
            caller: The authenticated user driving the agent run.

        Returns:
            A ``(agent, workflow_session)`` tuple: the ADK agent configured for
            the session's skill revision, and the WorkflowSession record itself.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner, a
                designated approver of the session, nor a super admin.
            SkillNotReadyError: If neither the revision the session pinned nor
                the skill's current revision is present in the store — the skill
                has never been cloned, or its store was wiped. An admin fixes it
                by pulling the skill.
        """
        ws = await self.get(ws_id, caller=caller)
        skill = await self._skills.get(ws.agent_skill_id)
        if skill is None:
            raise SkillNotReadyError(ws.agent_skill_id)

        # Sessions created before the store was revisioned pinned no revision;
        # they get the skill's current one.
        commit_sha = ws.agent_skill_commit_sha or skill.commit_sha
        if commit_sha is None:
            raise SkillNotReadyError(skill.id)

        skill_dir = self._skills_store.skill_dir(skill, commit_sha)
        if not skill_dir.exists():
            # The pinned revision is gone (a wiped volume, or a prune that
            # outran a session's insert). The skill's current revision is the
            # only code left to run, so fall back to it rather than stranding
            # the conversation -- loudly, because it is not the code the session
            # started with.
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
            ws.agent_skill_id, commit_sha, skill_dir, kind=AgentKind.execution
        )
        return agent, ws

    async def get_messages(
        self, ws_id: str, *, caller: User
    ) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a WorkflowSession's ADK session.

        The ADK session is looked up by the WorkflowSession's owner
        (``ws.user_id``), so the same history is returned regardless of which
        authorized user requests it — a designated approver opening the chat
        sees the owner's conversation instead of starting a fresh session.
        Returns an empty list when the ADK session does not exist yet (before
        the first agent run).

        Args:
            ws_id: Identifier of the WorkflowSession whose messages to fetch.
            caller: The authenticated user requesting the history.

        Returns:
            The session's messages as plain JSON-serializable dicts (the same
            shape as ``GET /sessions/{id}/messages``).

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
            ForbiddenError: If the caller is neither the session owner, a
                designated approver of the session, nor a super admin.
        """
        ws = await self.get(ws_id, caller=caller)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if session is None:
            return []
        messages = adk_events_to_messages(session.events)
        meta = await self._meta.meta_for_session(ws_id)
        result: builtins.list[dict[str, Any]] = []
        for message in messages:
            data = message.model_dump(mode="json", by_alias=True)
            # "user" and "assistant" messages keep the ADK event id as their
            # own id, but `adk_events_to_messages` regenerates a fresh random
            # id for every "tool" message on each call -- their only stable,
            # round-trip-safe correlation key is the tool_call_id they resolve.
            key = data.get("toolCallId") if data.get("role") == "tool" else data["id"]
            row = meta.get(key) if key is not None else None
            data["senderUserId"] = row.sender_user_id if row is not None else None
            data["workflowTaskId"] = row.workflow_task_id if row is not None else None
            result.append(data)
        return result

    async def attributable_keys(self, ws_id: str) -> set[str]:
        """Return the correlation keys of the session's attributable events.

        Two kinds of events can be attributed to a sender: ADK ``"user"``
        events (keyed by their own event id) and tool-response
        (function-response) events -- including A2UI user-action
        acknowledgements -- keyed by their function response id (the
        ``tool_call_id`` the frontend sent). Snapshotting this set before an
        agent run lets the router attribute whatever appears afterwards to the
        user who drove the run. Returns an empty set when the ADK session does
        not exist yet (before the first run).

        Args:
            ws_id: Identifier of the WorkflowSession whose events to read.

        Returns:
            The set of correlation keys (event ids and tool_call_ids)
            representing attributable events already present in the session.

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
        """
        ws = await self._get(ws_id)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if session is None:
            return set()
        keys: set[str] = set()
        for event in session.events:
            if event.author == "user":
                keys.add(event.id)
            for fr in event.get_function_responses():
                if fr.id:
                    keys.add(fr.id)
        return keys

    async def record_new_senders(
        self, ws_id: str, prior_keys: set[str], sender_user_id: str
    ) -> None:
        """Attribute the session's new attributable events to ``sender_user_id``.

        Compares the session's current attributable keys (see
        :meth:`attributable_keys`) against the snapshot taken before the run;
        every key not in ``prior_keys`` was produced by the current user, so it
        is recorded (idempotently) -- new ``"user"`` events by their event id,
        and new tool-response events (including A2UI action acknowledgements)
        by their tool_call_id. Tool responses matching
        :data:`_RENDER_ACK_RESPONSE` are skipped: they are the no-op
        acknowledgements the frontend flushes for every still-pending render
        call on the user's next run, not actions the user performed, and
        attributing them would paint the user's avatar onto surfaces they never
        touched. Does nothing when the ADK session does not exist.

        Args:
            ws_id: Identifier of the WorkflowSession that was run.
            prior_keys: The attributable keys present before the run.
            sender_user_id: The user who sent the new messages.

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
            ForeignKeyViolationError: If ``sender_user_id`` does not match a user.
        """
        ws = await self._get(ws_id)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if session is None:
            return
        for event in session.events:
            if event.author == "user" and event.id not in prior_keys:
                await self._meta.set_sender(
                    workflow_session_id=ws_id,
                    adk_event_id=event.id,
                    sender_user_id=sender_user_id,
                )
            for fr in event.get_function_responses():
                if fr.response == _RENDER_ACK_RESPONSE:
                    continue
                if fr.id and fr.id not in prior_keys:
                    await self._meta.set_sender(
                        workflow_session_id=ws_id,
                        adk_event_id=fr.id,
                        sender_user_id=sender_user_id,
                    )

    async def record_message_tasks(self, ws_id: str) -> None:
        """Associate each ADK event with the WorkflowTask in progress at the time.

        The agent drives the task lifecycle by calling ``update_workflow_task``
        with ``status="in_progress"`` before working on a task. Walking the
        session's events in order and tracking the most recent such transition
        therefore yields, for every event, the task that was in progress when it
        was produced. Each event from the first ``in_progress`` transition onward
        is recorded against its task (idempotently); events before any
        transition (the initial planning exchange) are left unassociated.
        Non-``in_progress`` transitions (e.g. ``completed``) do not change the
        current task, so a task's own wrap-up stays grouped under it. Does
        nothing when the ADK session does not exist.

        Args:
            ws_id: Identifier of the WorkflowSession that was run.

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
        """
        ws = await self._get(ws_id)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if session is None:
            return
        # Capture the audit user before the loop: each set_task commit expires
        # the ``ws`` instance, and re-reading ``ws.created_by`` afterwards would
        # trigger a lazy load outside the async greenlet context.
        owner_id = ws.created_by
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
                    workflow_session_id=ws_id,
                    adk_event_id=event.id,
                    workflow_task_id=current_task_id,
                    user_id=owner_id,
                )

    async def delete(self, ws_id: str, *, caller: User) -> None:
        """Delete a WorkflowSession and its underlying ADK chat session.

        Deletion is stricter than the shared-chat access rule: only the
        session owner or a super admin may delete a session — a designated
        approver may participate in the chat but not destroy it.

        Removes, in order: the ADK chat session keyed by the record's
        ``session_id`` (best effort — skipped if it no longer exists), then the
        WorkflowSession row itself. Deleting the row cascades to its
        WorkflowTasks (and their dependency edges and tool bindings) via the
        ``ON DELETE CASCADE`` foreign keys.

        Args:
            ws_id: Identifier of the session to delete.
            caller: The authenticated user requesting the deletion.

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
        """
        ws = await self._get(ws_id)
        self._access.assert_owner(ws.user_id, caller)
        existing = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if existing is not None:
            await self._session_service.delete_session(
                app_name=self._app_name,
                user_id=ws.user_id,
                session_id=ws.session_id,
            )
        await self._ws_repo.delete(ws_id)
