"""Use case service for AgentSkill resources.

Wraps the :class:`AgentSkillRepository` with the business rules the routers
need (notably raising :class:`NotFoundError` when a skill is missing) so the
router layer never touches the repository directly.
"""

from collections.abc import Sequence

from infrastructure.secret_resolver import split_secret_ref
from infrastructure.skill_manager import SkillManager
from models.agent_skill import (
    AgentSkill,
    AgentSkillCreate,
    AgentSkillRead,
    AgentSkillUpdate,
    SkillSyncStatus,
)
from repositories.agent_skill import AgentSkillRepository
from repositories.exceptions import (
    AgentSkillValidationError,
    ForeignKeyViolationError,
    NotFoundError,
    SkillNotReadyError,
)
from repositories.query import FilterSpec, SortSpec
from repositories.secret import SecretRepository

#: Alias for ``list[AgentSkillRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[AgentSkillRead]

_SKILL_MD_FILENAME = "SKILL.md"


class AgentSkillService:
    """Application service orchestrating AgentSkill operations."""

    def __init__(
        self,
        repo: AgentSkillRepository,
        secrets: SecretRepository,
        skill_manager: SkillManager,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing AgentSkill persistence.
            secrets: Repository used to check that a ``repo_auth_password``
                names a Secret the caller may see, at create/update time.
            skill_manager: The git-backed skill store, used to locate a
                published revision's SKILL.md.
        """
        self._repo = repo
        self._secrets = secrets
        self._skill_manager = skill_manager

    async def _check_auth_password(self, repo_url: str, ref: str | None) -> None:
        """Raise unless ``ref`` is unset or safe to send to ``repo_url``.

        Called with the *effective* values -- for an update, the stored ones
        wherever the PATCH leaves a field out -- because the clone sends the
        decrypted password to whatever ``repo_url`` the row holds: pointing an
        existing skill somewhere new must pass the same checks as binding the
        secret in the first place.

        The name half of the ``NAME/KEY`` reference must name a Secret the
        caller can see; a secret hidden by an access-control tag is reported
        exactly like a missing one. Whether the key exists is deliberately left
        to clone time: a ``vault`` secret's keys live in Vault and would need a
        live read, so checking here would make the two secret types behave
        differently. The reference is by name, not by foreign key, so a later
        rename or delete of the secret still fails lazily at clone time.

        Args:
            repo_url: The effective repository URL.
            ref: The effective ``repo_auth_password``, or ``None``.

        Raises:
            ForeignKeyViolationError: If the named secret does not exist or is
                hidden from the caller.
            AgentSkillValidationError: If a password would be sent to a plain
                ``http://`` URL.
        """
        if ref is None:
            return
        if repo_url.startswith("http://"):
            raise AgentSkillValidationError(
                "repo_auth_password requires an https:// repo_url: "
                "basic auth over http:// sends the password in the clear"
            )
        name, _ = split_secret_ref(ref)
        if await self._secrets.get_visible_by_name(name) is None:
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
                that does not exist or is hidden from the caller.
            AgentSkillValidationError: If ``repo_auth_password`` is set on an
                ``http://`` ``repo_url``.
        """
        await self._check_auth_password(str(data.repo_url), data.repo_auth_password)
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
            ForeignKeyViolationError: If the effective ``repo_auth_password``
                names a Secret that does not exist or is hidden from the caller.
            AgentSkillValidationError: If the effective ``repo_auth_password``
                is set on an ``http://`` ``repo_url``.
        """
        existing = await self.get(skill_id)
        sent = data.model_fields_set
        await self._check_auth_password(
            str(data.repo_url) if data.repo_url is not None else existing.repo_url,
            data.repo_auth_password
            if "repo_auth_password" in sent
            else existing.repo_auth_password,
        )
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

    async def get_content(self, skill_id: str) -> str:
        """Return the raw SKILL.md text for a skill's published revision.

        Args:
            skill_id: Identifier of the skill to read.

        Returns:
            The SKILL.md file's contents, verbatim.

        Raises:
            NotFoundError: If no skill exists with the given ID.
            SkillNotReadyError: If the skill has no published revision yet.
        """
        skill = await self.get(skill_id)
        if skill.commit_sha is None:
            raise SkillNotReadyError(skill.id)
        skill_dir = self._skill_manager.skill_dir(skill, skill.commit_sha)
        return (skill_dir / _SKILL_MD_FILENAME).read_text(encoding="utf-8")
