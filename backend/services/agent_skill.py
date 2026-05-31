"""Use case service for AgentSkill resources.

Wraps the :class:`AgentSkillRepository` with the business rules the routers
need (notably raising :class:`NotFoundError` when a skill is missing) so the
router layer never touches the repository directly.
"""

from collections.abc import Sequence

from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from repositories import AgentSkillRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class AgentSkillService:
    """Application service orchestrating AgentSkill operations."""

    def __init__(self, repo: AgentSkillRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing AgentSkill persistence.
        """
        self._repo = repo

    async def get(self, skill_id: str) -> AgentSkill:
        """Return the AgentSkill with the given ID.

        Args:
            skill_id: Identifier of the skill to fetch.

        Returns:
            The matching AgentSkill.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        skill = await self._repo.get(skill_id)
        if skill is None:
            raise NotFoundError("AgentSkill", skill_id)
        return skill

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[AgentSkill]:
        """Return a page of AgentSkill records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of skills.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: AgentSkillCreate, *, user_id: str) -> AgentSkill:
        """Create a new AgentSkill.

        Args:
            data: Fields for the new skill.
            user_id: ID of the user creating the skill.

        Returns:
            The created AgentSkill.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, skill_id: str, data: AgentSkillUpdate, *, user_id: str
    ) -> AgentSkill:
        """Apply a partial update to an AgentSkill.

        Args:
            skill_id: Identifier of the skill to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated AgentSkill.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        return await self._repo.update(skill_id, data, user_id=user_id)

    async def delete(self, skill_id: str) -> None:
        """Delete an AgentSkill.

        Args:
            skill_id: Identifier of the skill to delete.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        await self._repo.delete(skill_id)
