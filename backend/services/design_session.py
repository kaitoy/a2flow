"""Use case service for DesignSession resources.

Exposes DesignSession reads and resolution of the design agent bound to a
session. A design session is the chat in which a workflow's task templates
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

from infrastructure.agent import AgentKind, AgentRegistry, tenant_app_name
from infrastructure.skill_manager import SkillManager
from models.design_session import DesignSession
from models.user import Role, User, has_role
from repositories import AgentSkillRepository, DesignSessionRepository
from repositories.exceptions import (
    ForbiddenError,
    NotFoundError,
    SkillNotReadyError,
)

logger = logging.getLogger(__name__)


def build_design_transcript(events: list[Event]) -> str:
    """Render a design session's ADK events as a plain-text transcript.

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


class DesignSessionService:
    """Application service orchestrating DesignSession operations."""

    def __init__(
        self,
        ds_repo: DesignSessionRepository,
        skills: AgentSkillRepository,
        skills_store: SkillManager,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        """Initialize the service.

        Args:
            ds_repo: Repository providing DesignSession persistence.
            skills: Repository providing AgentSkill persistence, read to
                resolve the ``repo_path`` and fallback revision of a session's
                skill.
            skills_store: Store locating a skill revision's directory on disk.
            registry: Registry resolving ADK agents per skill revision and kind.
            session_service: ADK session store holding the chat history.
            app_name: ADK application name keying sessions in the store.
        """
        self._ds_repo = ds_repo
        self._skills = skills
        self._skills_store = skills_store
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name

    @staticmethod
    def _assert_owner(ds: DesignSession, caller: User) -> None:
        """Reject callers who are neither the session owner nor a super admin.

        Args:
            ds: The design session being operated on.
            caller: The authenticated user performing the operation.

        Raises:
            ForbiddenError: If the caller is not the session owner and not a
                super admin.
        """
        if caller.id == ds.user_id or has_role(caller, Role.super_admin):
            return
        raise ForbiddenError("Only the session owner can access this design session")

    async def _get(self, ds_id: str) -> DesignSession:
        """Return the DesignSession with the given ID, without authorization.

        Args:
            ds_id: Identifier of the session to fetch.

        Returns:
            The matching DesignSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ds = await self._ds_repo.get(ds_id)
        if ds is None:
            raise NotFoundError("DesignSession", ds_id)
        return ds

    async def get(self, ds_id: str, *, caller: User) -> DesignSession:
        """Return the DesignSession with the given ID, authorizing the caller.

        Args:
            ds_id: Identifier of the session to fetch.
            caller: The authenticated user requesting the session.

        Returns:
            The matching DesignSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
        """
        ds = await self._get(ds_id)
        self._assert_owner(ds, caller)
        return ds

    async def get_for_workflow(self, workflow_id: str) -> DesignSession:
        """Return the design session belonging to a workflow.

        Args:
            workflow_id: Identifier of the workflow whose session to fetch.

        Returns:
            The workflow's DesignSession.

        Raises:
            NotFoundError: If the workflow has no design session (or does not
                exist).
        """
        ds = await self._ds_repo.get_by_workflow_id(workflow_id)
        if ds is None:
            raise NotFoundError("DesignSession", workflow_id)
        return ds

    async def resolve_agent(
        self, ds_id: str, *, caller: User
    ) -> tuple[ADKAgent, DesignSession]:
        """Resolve the design agent bound to a DesignSession and the record.

        Mirrors ``WorkflowSessionService.resolve_agent``: the skill revision
        pinned on the record is loaded from the shared store, falling back to
        the skill's current revision (loudly) when the pinned directory is
        gone, and the agent is resolved with :attr:`AgentKind.design` so the
        chat runs under the interactive design instruction and toolset.

        Args:
            ds_id: Identifier of the session whose agent to resolve.
            caller: The authenticated user driving the agent run.

        Returns:
            An ``(agent, design_session)`` tuple.

        Raises:
            NotFoundError: If no session exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
            SkillNotReadyError: If neither the pinned revision nor the skill's
                current revision is present in the store.
        """
        ds = await self.get(ds_id, caller=caller)
        skill = await self._skills.get(ds.agent_skill_id)
        if skill is None:
            raise SkillNotReadyError(ds.agent_skill_id)

        commit_sha = ds.agent_skill_commit_sha
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
            ds.agent_skill_id,
            commit_sha,
            skill_dir,
            tenant_id=ds.tenant_id,
            kind=AgentKind.design,
        )
        return agent, ds

    async def get_messages(
        self, ds_id: str, *, caller: User
    ) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a DesignSession's ADK session.

        The history is keyed by the session's owner. Returns an empty list when
        the ADK session does not exist yet (the background generation run has
        not started). ``senderUserId`` and ``workflowTaskId`` are included as
        ``None`` so the payload shape matches the workflow-session messages
        endpoint and the frontend chat components can be reused unchanged.

        Args:
            ds_id: Identifier of the DesignSession whose messages to fetch.
            caller: The authenticated user requesting the history.

        Returns:
            The session's messages as plain JSON-serializable dicts.

        Raises:
            NotFoundError: If no DesignSession exists with the given ID.
            ForbiddenError: If the caller is neither the session owner nor a
                super admin.
        """
        ds = await self.get(ds_id, caller=caller)
        session = await self._session_service.get_session(
            app_name=tenant_app_name(self._app_name, ds.tenant_id),
            user_id=ds.user_id,
            session_id=ds.session_id,
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
