"""Use case service for Workflow resources.

Holds the Workflow CRUD operations plus the multi-collaborator ``execute``
orchestration (resolve workflow → resolve skill → clone skill → create a
WorkflowSession) that previously lived inline in the router.
"""

import uuid
from collections.abc import Sequence

from infrastructure.secret_resolver import SecretResolver
from infrastructure.skill_manager import SkillManager
from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from models.workflow_session import WorkflowSession, WorkflowSessionCreate
from repositories import (
    AgentSkillRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
)
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec

#: Basic-auth username used for a skill clone when the skill names an auth
#: secret but no explicit ``repo_auth_username``. Works for GitHub PATs, where
#: the username is ignored as long as the token is the password.
_DEFAULT_GIT_USERNAME = "x-access-token"


class WorkflowService:
    """Application service orchestrating Workflow operations."""

    def __init__(
        self,
        workflows: WorkflowRepository,
        skills: AgentSkillRepository,
        skill_manager: SkillManager,
        ws_repo: WorkflowSessionRepository,
        resolver: SecretResolver,
    ) -> None:
        """Initialize the service.

        Args:
            workflows: Repository providing Workflow persistence.
            skills: Repository providing AgentSkill persistence.
            skill_manager: Manager that clones skill repositories locally.
            ws_repo: Repository providing WorkflowSession persistence.
            resolver: Resolver turning a skill's ``repo_auth_secret`` into the
                clone credential.
        """
        self._workflows = workflows
        self._skills = skills
        self._skill_manager = skill_manager
        self._ws_repo = ws_repo
        self._resolver = resolver

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

    async def create(self, data: WorkflowCreate, *, user_id: str) -> Workflow:
        """Create a new Workflow.

        Args:
            data: Fields for the new workflow.
            user_id: ID of the user creating the workflow.

        Returns:
            The created Workflow.
        """
        return await self._workflows.create(data, user_id=user_id)

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
        """Start a workflow run by creating a WorkflowSession.

        Resolves the workflow and its skill, ensures the skill repository is
        cloned locally, and records a new WorkflowSession. The ADK session is
        created lazily on the first agent call.

        Args:
            workflow_id: Identifier of the workflow to execute.
            user_id: ID of the user starting the run (empty falls back to
                ``"user"``).

        Returns:
            The created WorkflowSession.

        Raises:
            NotFoundError: If the workflow or its skill does not exist.
            SecretResolutionError: If the skill's ``repo_auth_secret`` cannot
                be resolved.
        """
        workflow = await self.get(workflow_id)
        skill = await self._skills.get(workflow.agent_skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", workflow.agent_skill_id)

        auth: tuple[str, str] | None = None
        if skill.repo_auth_secret is not None:
            token = await self._resolver.resolve_value(skill.repo_auth_secret)
            auth = (skill.repo_auth_username or _DEFAULT_GIT_USERNAME, token)
        skill_dir = await self._skill_manager.ensure_cloned(skill, auth=auth)
        user = user_id or "user"
        session_id = str(uuid.uuid4())

        ws_create = WorkflowSessionCreate(
            session_id=session_id,
            workflow_name=workflow.name,
            workflow_prompt=workflow.prompt,
            workflow_description=workflow.description,
            agent_skill_id=skill.id,
            agent_skill_name=skill.name,
            agent_skill_repo_url=skill.repo_url,
            agent_skill_repo_path=skill.repo_path,
            skill_dir=str(skill_dir),
            user_id=user,
        )
        return await self._ws_repo.create(
            ws_create, workflow_id=workflow.id, user_id=user
        )
