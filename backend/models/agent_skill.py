"""AgentSkill data models for create, update, and database persistence."""

from datetime import datetime
from enum import StrEnum

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z_or_none
from models.constraints import (
    DescText,
    EntityName,
    GitRef,
    GitUsername,
    HttpUrl,
    RepoPath,
    SecretRef,
)
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class SkillSyncStatus(StrEnum):
    """Outcome of the most recent clone/pull of a skill's repository.

    Deliberately separate from usability: whether a skill can back a workflow
    run is decided by :attr:`AgentSkill.commit_sha`, not by this field. A pull
    that fails leaves the previously published revision in place, so the skill
    keeps working at the old revision while the UI surfaces ``failed`` and the
    reason.
    """

    pending = "pending"
    """A clone/pull is queued or in flight."""

    ready = "ready"
    """The last clone/pull published a revision successfully."""

    failed = "failed"
    """The last clone/pull failed; ``sync_error`` carries the reason."""


class AgentSkillUpdate(SQLModel):
    """Partial update payload for an AgentSkill — all fields are optional.

    ``repo_auth_password`` references one entry of a registered Secret in
    ``NAME/KEY`` form, whose value is used as the HTTP basic-auth password when
    cloning the repository, enabling private repos. The key is mandatory
    because a Secret holds a map of entries. ``repo_auth_username`` is the
    matching basic-auth username and defaults to ``x-access-token`` (suitable
    for GitHub PATs) when left unset. The secret is referenced by name and
    resolved at clone time, so renaming or deleting it later makes the next
    clone fail rather than the edit. ``repo_ref`` optionally names a branch or
    tag to clone instead of the repository's default branch; every clone/pull
    re-resolves it, so a moved branch tip or a re-pointed tag is picked up on
    the next sync.
    """

    model_config = _alias_config
    name: EntityName | None = None
    repo_url: HttpUrl | None = None
    repo_path: RepoPath | None = None
    repo_ref: GitRef | None = None
    description: DescText | None = None
    repo_auth_password: SecretRef | None = None
    repo_auth_username: GitUsername | None = None


class AgentSkillCreate(AgentSkillUpdate):
    """Creation payload for an AgentSkill with required fields."""

    name: EntityName
    repo_url: HttpUrl
    repo_path: RepoPath = ""


class AgentSkill(AgentSkillCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted agent skill referencing a Git repository of ADK tools.

    The sync fields below are server-managed: they are declared on the table
    class only, so they are absent from ``AgentSkillCreate`` /
    ``AgentSkillUpdate`` and cannot be written through the API. They are set by
    the clone/pull job (``services/agent_skill_sync.py``), which is scheduled
    when the skill is registered and re-run on demand from
    ``POST /agent-skills/{id}/pull``.

    ``commit_sha`` is the contract with the rest of the system: it names the
    revision directory published under ``Settings.skills_dir`` and, being
    non-null only once a complete revision exists, is what gates whether a
    workflow may run on this skill.
    """

    __tablename__ = "agent_skills"

    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    sync_status: SkillSyncStatus = Field(default=SkillSyncStatus.pending)
    sync_error: str | None = None
    commit_sha: str | None = None
    synced_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_agent_skills_tenant_id_name"),
        Index("ix_agent_skills_tenant_id_name", "tenant_id", "name"),
    )

    @field_serializer("synced_at", when_used="json")
    def _serialize_synced_at(self, dt: datetime | None) -> str | None:
        """Serialize the sync timestamp as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return iso_z_or_none(dt)


class AgentSkillRead(BaseEntity):
    """Read view of an AgentSkill returned by the API, including its tags.

    Mirrors every column of :class:`AgentSkill` and adds ``tag_ids``, which
    lives in :class:`models.tag.AgentSkillTag` rather than on the skill row. The
    mirroring is not cosmetic: this class is what
    :meth:`repositories.agent_skill.SqlAgentSkillRepository.list` passes as
    ``readable=``, and a column missing here becomes unfilterable and
    unsortable through the list API.

    ``synced_at`` repeats the table class's serializer for the same reason it
    exists there: the generated frontend schemas reject the ``+00:00`` offset
    Pydantic emits by default.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    repo_url: str
    repo_path: str = ""
    repo_ref: str | None = None
    description: str | None = None
    repo_auth_password: str | None = None
    repo_auth_username: str | None = None
    sync_status: SkillSyncStatus = SkillSyncStatus.pending
    sync_error: str | None = None
    commit_sha: str | None = None
    synced_at: datetime | None = None
    #: Ids of the tags attached to this skill.
    tag_ids: list[str] = []

    @field_serializer("synced_at", when_used="json")
    def _serialize_synced_at(self, dt: datetime | None) -> str | None:
        """Serialize the sync timestamp as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return iso_z_or_none(dt)

    @classmethod
    def from_skill(cls, skill: AgentSkill, *, tag_ids: list[str]) -> "AgentSkillRead":
        """Build the read view of a stored skill with its tags attached.

        Args:
            skill: The persisted skill to project.
            tag_ids: Ids of the tags attached to ``skill``.

        Returns:
            A read view carrying the skill's columns plus its tags.
        """
        return cls(**skill.model_dump(), tag_ids=tag_ids)
