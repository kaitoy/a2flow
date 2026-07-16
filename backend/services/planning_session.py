"""Use case service for PlanningSession resources.

Exposes PlanningSession reads and resolution of the planning agent bound to a
session. A planning session is the chat in which a workflow's task templates
are produced and refined; unlike workflow sessions it has no approver sharing —
only the owner (and super admins) may use it — so no separate access policy is
needed.
"""

import builtins
import logging
from typing import Any

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.events import Event
from google.adk.sessions import BaseSessionService

from infrastructure.agent import AgentKind, AgentRegistry
from infrastructure.skill_manager import SkillManager
from models.planning_session import PlanningSession
from models.user import Role, User, has_role
from repositories import AgentSkillRepository, PlanningSessionRepository
from repositories.exceptions import (
    ForbiddenError,
    NotFoundError,
    SkillNotReadyError,
)

logger = logging.getLogger(__name__)


def build_planning_transcript(events: list[Event]) -> str:
    """Render a planning session's ADK events as a plain-text transcript.

    Keeps only plain-text ``user`` and ``assistant`` turns (tool calls and
    their results are noise for summarization) and prefixes each line with its
    speaker.

    Args:
        events: The ADK session's events, oldest first.

    Returns:
        The transcript, one ``Speaker: text`` paragraph per message.
    """
    lines: builtins.list[str] = []
    for message in adk_events_to_messages(events):
        data = message.model_dump(mode="json", by_alias=True)
        role = data.get("role")
        content = data.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        text = content.strip()
        if text:
            lines.append(f"{role.capitalize()}: {text}")
    return "\n\n".join(lines)


class PlanningSessionService:
    """Application service orchestrating PlanningSession operations."""

    def __init__(
        self,
        ps_repo: PlanningSessionRepository,
        skills: AgentSkillRepository,
        skills_store: SkillManager,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        """Initialize the service.

        Args:
            ps_repo: Repository providing PlanningSession persistence.
            skills: Repository providing AgentSkill persistence, read to
                resolve the ``repo_path`` and fallback revision of a session's
                skill.
            skills_store: Store locating a skill revision's directory on disk.
            registry: Registry resolving ADK agents per skill revision and kind.
            session_service: ADK session store holding the chat history.
            app_name: ADK application name keying sessions in the store.
        """
        self._ps_repo = ps_repo
        self._skills = skills
        self._skills_store = skills_store
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name

    @staticmethod
    def _assert_owner(ps: PlanningSession, caller: User) -> None:
        """Reject callers who are neither the session owner nor a super admin.

        Args:
            ps: The planning session being operated on.
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the session owner and not a
                super admin.
        """
        if caller.id == ps.user_id or has_role(caller, Role.super_admin):
            return
        raise ForbiddenError("Only the session owner can access this planning session")

    async def _get(self, ps_id: str) -> PlanningSession:
        """Return the PlanningSession with the given ID, without authorization.

        Args:
            ps_id: Identifier of the session to fetch.

        Returns:
            The matching PlanningSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ps = await self._ps_repo.get(ps_id)
        if ps is None:
            raise NotFoundError("PlanningSession", ps_id)
        return ps

    async def get(self, ps_id: str, *, caller: User) -> PlanningSession:
        """Return the PlanningSession with the given ID, authorizing the caller.

        Args:
            ps_id: Identifier of the session to fetch.
            caller: The authenticated user requesting the session.

        Returns:
            The matching PlanningSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
        """
        ps = await self._get(ps_id)
        self._assert_owner(ps, caller)
        return ps

    async def get_for_workflow(self, workflow_id: str) -> PlanningSession:
        """Return the planning session belonging to a workflow.

        Args:
            workflow_id: Identifier of the workflow whose session to fetch.

        Returns:
            The workflow's PlanningSession.

        Raises:
            NotFoundError: If the workflow has no planning session (or does not
                exist).
        """
        ps = await self._ps_repo.get_by_workflow_id(workflow_id)
        if ps is None:
            raise NotFoundError("PlanningSession", workflow_id)
        return ps

    async def resolve_agent(
        self, ps_id: str, *, caller: User
    ) -> tuple[ADKAgent, PlanningSession]:
        """Resolve the planning agent bound to a PlanningSession and the record.

        Mirrors ``WorkflowSessionService.resolve_agent``: the skill revision
        pinned on the record is loaded from the shared store, falling back to
        the skill's current revision (loudly) when the pinned directory is
        gone, and the agent is resolved with :attr:`AgentKind.planning` so the
        chat runs under the interactive planning instruction and toolset.

        Args:
            ps_id: Identifier of the session whose agent to resolve.
            caller: The authenticated user driving the agent run.

        Returns:
            An ``(agent, planning_session)`` tuple.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
            SkillNotReadyError: If neither the pinned revision nor the skill's
                current revision is present in the store.
        """
        ps = await self.get(ps_id, caller=caller)
        skill = await self._skills.get(ps.agent_skill_id)
        if skill is None:
            raise SkillNotReadyError(ps.agent_skill_id)

        commit_sha = ps.agent_skill_commit_sha
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
            ps.agent_skill_id, commit_sha, skill_dir, kind=AgentKind.planning
        )
        return agent, ps

    async def get_messages(
        self, ps_id: str, *, caller: User
    ) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a PlanningSession's ADK session.

        The history is keyed by the session's owner. Returns an empty list when
        the ADK session does not exist yet (the background generation run has
        not started). ``senderUserId`` and ``workflowTaskId`` are included as
        ``None`` so the payload shape matches the workflow-session messages
        endpoint and the frontend chat components can be reused unchanged.

        Args:
            ps_id: Identifier of the PlanningSession whose messages to fetch.
            caller: The authenticated user requesting the history.

        Returns:
            The session's messages as plain JSON-serializable dicts.

        Raises:
            NotFoundError: If no PlanningSession exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
        """
        ps = await self.get(ps_id, caller=caller)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ps.user_id,
            session_id=ps.session_id,
        )
        if session is None:
            return []
        result: builtins.list[dict[str, Any]] = []
        for message in adk_events_to_messages(session.events):
            data = message.model_dump(mode="json", by_alias=True)
            data["senderUserId"] = None
            data["workflowTaskId"] = None
            result.append(data)
        return result
