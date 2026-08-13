"""Use case service for AgentSkill resources.

Wraps the :class:`AgentSkillRepository` with the business rules the routers
need (notably raising :class:`NotFoundError` when a skill is missing) so the
router layer never touches the repository directly.
"""

from collections.abc import Sequence

from infrastructure.secret_resolver import split_secret_ref
from models.agent_skill import (
    AgentSkill,
    AgentSkillCreate,
    AgentSkillRead,
    AgentSkillUpdate,
    SkillSyncStatus,
)
from repositories import AgentSkillRepository, SecretRepository
from repositories.exceptions import ForeignKeyViolationError, NotFoundError
from repositories.query import FilterSpec, SortSpec

#: Alias for ``list[AgentSkillRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[AgentSkillRead]


class AgentSkillService:
    """Application service orchestrating AgentSkill operations."""

    def __init__(self, repo: AgentSkillRepository, secrets: SecretRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing AgentSkill persistence.
            secrets: Repository used to check that a ``repo_auth_password``
                names an existing Secret at create/update time.
        """
        self._repo = repo
        self._secrets = secrets

    async def _check_auth_password(self, ref: str | None) -> None:
        """Raise if ``ref`` is set but names no existing Secret.

        Only the name half of the ``NAME/KEY`` reference is checked. Whether the
        key exists is deliberately left to clone time: a ``vault`` secret's keys
        live in Vault and would need a live read, so checking here would make
        the two secret types behave differently. This is a friendliness check at
        edit time only — the reference is by name, not by foreign key, so a
        later rename or delete of the secret still fails lazily at clone time.

        Args:
            ref: The ``repo_auth_password`` value from the payload, or ``None``.

        Raises:
            ForeignKeyViolationError: If the named secret does not exist.
        """
        if ref is None:
            return
        name, _ = split_secret_ref(ref)
        if await self._secrets.get_by_name(name) is None:
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
        tag_ids: Sequence[str] = (),
    ) -> list[AgentSkill]:
        """Return a page of AgentSkill records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            tag_ids: Narrows the page to skills carrying every listed tag.

        Returns:
            The requested page of skills.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, skill: AgentSkill) -> AgentSkillRead:
        """Project one AgentSkill into its API read view, attaching its tags.

        Args:
            skill: The persisted skill to project.

        Returns:
            The read view, with tag ids attached.
        """
        return AgentSkillRead.from_skill(
            skill, tag_ids=await self._repo.tag_ids_for(skill.id)
        )

    async def to_read_many(self, skills: Sequence[AgentSkill]) -> _ReadList:
        """Project a page of AgentSkills into read views, reading their tags in one query.

        Args:
            skills: The persisted records to project.

        Returns:
            The read views, in the order they were given.
        """
        by_id = await self._repo.tag_ids_for_many([x.id for x in skills])
        return [
            AgentSkillRead.from_skill(x, tag_ids=by_id.get(x.id, [])) for x in skills
        ]

    async def set_tags(self, skill_id: str, tag_ids: Sequence[str]) -> AgentSkill:
        """Replace a AgentSkill's tag attachments wholesale.

        Args:
            skill_id: Identifier of the skill to retag.
            tag_ids: Ids of the tags it should carry.

        Returns:
            The skill, unchanged apart from its attachments.

        Raises:
            NotFoundError: If no skill exists with the given ID.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        return await self._repo.set_tags(skill_id, tag_ids)

    async def create(self, data: AgentSkillCreate, *, user_id: str) -> AgentSkill:
        """Create a new AgentSkill.

        Args:
            data: Fields for the new skill.
            user_id: ID of the user creating the skill.

        Returns:
            The created AgentSkill.

        Raises:
            ForeignKeyViolationError: If ``repo_auth_password`` names a Secret
                that does not exist.
        """
        await self._check_auth_password(data.repo_auth_password)
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
            ForeignKeyViolationError: If ``repo_auth_password`` names a Secret
                that does not exist.
        """
        await self._check_auth_password(data.repo_auth_password)
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
