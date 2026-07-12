"""Use case service for AgentSkill resources.

Wraps the :class:`AgentSkillRepository` with the business rules the routers
need (notably raising :class:`NotFoundError` when a skill is missing) so the
router layer never touches the repository directly.
"""

from collections.abc import Sequence

from models.agent_skill import (
    AgentSkill,
    AgentSkillCreate,
    AgentSkillUpdate,
    SkillSyncStatus,
)
from repositories import AgentSkillRepository, SecretRepository
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from repositories.query import FilterSpec, SortSpec


class AgentSkillService:
    """Application service orchestrating AgentSkill operations."""

    def __init__(self, repo: AgentSkillRepository, secrets: SecretRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing AgentSkill persistence.
            secrets: Repository used to check that a ``repo_auth_secret``
                names an existing Secret at create/update time.
        """
        self._repo = repo
        self._secrets = secrets

    async def _check_auth_secret(self, name: str | None) -> None:
        """Raise if ``name`` is set but no Secret with that name exists.

        This is a friendliness check at edit time only — the reference is by
        name, not by foreign key, so a later rename or delete of the secret
        still fails lazily at clone time.

        Args:
            name: The ``repo_auth_secret`` value from the payload, or ``None``.

        Raises:
            ForeignKeyViolationError: If the named secret does not exist.
        """
        if name is not None and await self._secrets.get_by_name(name) is None:
            raise ForeignKeyViolationError("Secret", name)

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

        Raises:
            ForeignKeyViolationError: If ``repo_auth_secret`` names a Secret
                that does not exist.
        """
        await self._check_auth_secret(data.repo_auth_secret)
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
            ForeignKeyViolationError: If ``repo_auth_secret`` names a Secret
                that does not exist.
        """
        await self._check_auth_secret(data.repo_auth_secret)
        return await self._repo.update(skill_id, data, user_id=user_id)

    async def mark_pending(self, skill_id: str, *, user_id: str) -> AgentSkill:
        """Mark a skill as awaiting a clone/pull, before the job is scheduled.

        Set synchronously by the pull route so the row the caller gets back --
        and the next list the admin UI polls -- already reads ``pending``,
        rather than briefly showing the previous outcome until the background
        job gets around to starting.

        This does not make a usable skill unusable: runnability is decided by
        ``commit_sha``, which this leaves alone.

        Args:
            skill_id: Identifier of the skill about to be synced.
            user_id: ID of the user requesting the sync.

        Returns:
            The updated AgentSkill.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        return await self._repo.set_sync_state(
            skill_id, status=SkillSyncStatus.pending, user_id=user_id
        )

    async def delete(self, skill_id: str) -> None:
        """Delete an AgentSkill.

        Args:
            skill_id: Identifier of the skill to delete.

        Raises:
            NotFoundError: If no skill exists with the given ID.
        """
        await self._repo.delete(skill_id)
