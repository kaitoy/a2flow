"""Knowledge base data models: an LLM-maintained wiki in Open Knowledge Format.

A :class:`KnowledgeBase` is a named, tenant-scoped wiki. Users register
:class:`KnowledgeSource` rows into it -- a URL or an uploaded document (PDF,
Word, plain text, Markdown, HTML) -- and a background job
(:mod:`services.knowledge_ingest`) has the LLM read each source and fold what
it says into topic-level :class:`KnowledgePage` rows, creating new pages or
rewriting existing ones. The pages are what workflow agents read at run time
(:mod:`infrastructure.knowledge_tools`); a workflow sees only the knowledge
bases linked to it through :class:`WorkflowKnowledgeBase`.

Each page is one *concept* of an `Open Knowledge Format
<https://github.com/GoogleCloudPlatform/open-knowledge-format>`_ (OKF v0.2)
bundle: YAML frontmatter plus a Markdown body. ``type``, ``title``, and
``description`` are real columns because search and the generated
``index.md`` read them; the rest of the frontmatter (``tags``, ``sources``,
``generated``) lives in :attr:`KnowledgePage.meta`. The bundle's reserved
``index.md`` files are never stored -- :mod:`infrastructure.okf` derives them
from the pages whenever they are read or exported.

A page cites the sources it draws on with keyed footnotes (``[^src-1a2b3c4d]``)
whose labels match :attr:`KnowledgeSource.citation_key`, the OKF convention
for per-claim attribution. That key is also how removing a source finds the
pages it has to rewrite.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import field_serializer, field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z, iso_z_or_none
from models.constraints import DescText, EntityName, HttpUrl
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Upper bound on the knowledge bases one workflow may be linked to.
MAX_WORKFLOW_KNOWLEDGE_BASES = 20


class KnowledgeSourceKind(StrEnum):
    """Where a knowledge source's content comes from."""

    url = "url"
    """A web page, fetched again on every (re-)ingest."""

    file = "file"
    """An uploaded document, whose bytes are stored on the row."""


class KnowledgeSourceStatus(StrEnum):
    """Lifecycle of a knowledge source's contribution to its wiki."""

    pending = "pending"
    """Registered; the ingest job is queued behind other jobs of the same knowledge base."""

    ingesting = "ingesting"
    """The LLM is reading the source and writing pages."""

    ready = "ready"
    """The source's knowledge is in the wiki."""

    failed = "failed"
    """The last job failed; ``error`` carries the reason and no page was changed by it."""

    removing = "removing"
    """Deletion was requested; the LLM is taking the source's claims out of the wiki."""


class KnowledgeBaseUpdate(SQLModel):
    """Partial update payload for a KnowledgeBase -- all fields are optional."""

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None


class KnowledgeBaseCreate(KnowledgeBaseUpdate):
    """Creation payload for a KnowledgeBase with required fields."""

    name: EntityName


class KnowledgeBase(KnowledgeBaseCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted knowledge base: one OKF bundle of LLM-written pages."""

    __tablename__ = "knowledge_bases"

    #: Redeclared without ``index=True``: the composite ``(tenant_id, name)``
    #: index below already serves tenant-only lookups through its leading column.
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_knowledge_bases_tenant_id_name"),
        Index("ix_knowledge_bases_tenant_id_name", "tenant_id", "name"),
    )


class KnowledgeBaseRead(BaseEntity):
    """Read view of a KnowledgeBase returned by the API, including its tags.

    Mirrors every column of :class:`KnowledgeBase` -- it is the ``readable=``
    schema of the list query -- and adds ``tag_ids``, which live in
    :class:`models.tag.KnowledgeBaseTag`.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    description: str | None = None
    #: Ids of the tags attached to this knowledge base.
    tag_ids: list[str] = []

    @classmethod
    def from_knowledge_base(
        cls, kb: KnowledgeBase, *, tag_ids: list[str]
    ) -> "KnowledgeBaseRead":
        """Build the read view of a stored knowledge base with its tags attached.

        Args:
            kb: The persisted knowledge base to project.
            tag_ids: Ids of the tags attached to ``kb``.

        Returns:
            A read view carrying the knowledge base's columns plus its tags.
        """
        return cls(**kb.model_dump(), tag_ids=tag_ids)


class KnowledgeUrlSourceCreate(SQLModel):
    """Request body registering a web page as a knowledge source.

    ``url`` goes through the shared SSRF check (``models.constraints.HttpUrl``);
    the fetch re-checks every hop right before connecting.
    """

    model_config = _alias_config
    url: HttpUrl


class KnowledgeSource(TenantScoped, BaseEntity, table=True):
    """One URL or uploaded document feeding a knowledge base.

    ``data`` holds an uploaded file's bytes and stays ``None`` for a URL, which
    is fetched afresh on each ingest so a re-ingest picks up the page's current
    content. ``title`` is filled in from the converted document once it has
    been read. Rows are deleted with their knowledge base (``ON DELETE
    CASCADE``).
    """

    __tablename__ = "knowledge_sources"

    knowledge_base_id: str
    kind: KnowledgeSourceKind
    url: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    data: bytes | None = Field(default=None, sa_type=LargeBinary)
    title: str | None = None
    status: KnowledgeSourceStatus = Field(default=KnowledgeSourceStatus.pending)
    error: str | None = None
    ingested_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_knowledge_sources_knowledge_base_id",
            ondelete="CASCADE",
        ),
        Index("ix_knowledge_sources_knowledge_base_id", "knowledge_base_id"),
    )

    @property
    def citation_key(self) -> str:
        """Return the footnote label pages use to cite this source.

        Taken from the **end** of the UUID7 id: its leading digits are a
        millisecond timestamp, shared by every source registered in the same
        minute, while the trailing ones are random.
        """
        return citation_key_for(self.id)

    @property
    def resource(self) -> str:
        """Return the OKF ``sources[].resource`` value: the URL, or the file name."""
        return self.url or self.file_name or self.id


def citation_key_for(source_id: str) -> str:
    """Return the footnote label of the source with the given id.

    Args:
        source_id: Id of a :class:`KnowledgeSource`.

    Returns:
        The ``src-xxxxxxxx`` label.
    """
    return f"src-{source_id.replace('-', '')[-8:]}"


class KnowledgeSourceRead(BaseEntity):
    """Read view of a KnowledgeSource: every column except the stored bytes."""

    model_config = _alias_config
    tenant_id: str
    knowledge_base_id: str
    kind: KnowledgeSourceKind
    url: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    title: str | None = None
    status: KnowledgeSourceStatus
    error: str | None = None
    ingested_at: datetime | None = None
    #: The footnote label pages use to cite this source.
    citation_key: str

    @field_serializer("ingested_at", when_used="json")
    def _serialize_ingested_at(self, dt: datetime | None) -> str | None:
        """Serialize the ingest timestamp as ISO-8601 with a ``Z`` suffix."""
        return iso_z_or_none(dt)

    @classmethod
    def from_source(cls, source: KnowledgeSource) -> "KnowledgeSourceRead":
        """Build the read view of a stored source, leaving its bytes behind.

        Args:
            source: The persisted source to project.

        Returns:
            The read view.
        """
        return cls(
            **source.model_dump(exclude={"data"}), citation_key=source.citation_key
        )


class KnowledgePage(TenantScoped, BaseEntity, table=True):
    """One OKF concept document of a knowledge base.

    ``path`` is the bundle-relative path with a leading ``/`` (for example
    ``/topics/vpn-setup.md``), unique within its knowledge base. ``meta``
    holds the frontmatter keys that are not columns: ``tags`` (a list of
    strings), ``sources`` (a list of ``{id, resource, title}`` mappings), and
    ``generated`` (``{by, at}``).
    """

    __tablename__ = "knowledge_pages"

    knowledge_base_id: str
    path: str
    type: str
    title: str
    description: str = ""
    body: str = Field(default="", sa_type=Text)
    meta: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_knowledge_pages_knowledge_base_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "path",
            name="uq_knowledge_pages_knowledge_base_id_path",
        ),
    )

    @property
    def source_ids(self) -> list[str]:
        """Return the citation keys listed in the page's ``sources``."""
        return [str(s.get("id")) for s in self.meta.get("sources", [])]


class KnowledgePageSummary(SQLModel):
    """One page as listed in a knowledge base's page browser."""

    model_config = _alias_config
    path: str
    type: str
    title: str
    description: str
    updated_at: datetime

    @field_serializer("updated_at", when_used="json")
    def _serialize_updated_at(self, dt: datetime) -> str:
        """Serialize the timestamp as ISO-8601 with a ``Z`` suffix."""
        return iso_z(dt)


class KnowledgePageContent(SQLModel):
    """One page as a complete OKF document: frontmatter and body in one Markdown text."""

    model_config = _alias_config
    path: str
    title: str
    #: The page exactly as it appears in an exported bundle.
    content: str


class WorkflowKnowledgeBase(SQLModel, table=True):
    """Join row linking one Workflow to one KnowledgeBase it may read.

    Live rather than snapshotted with the published design: a knowledge base
    is mutable data, so a run reads the links as they are when it runs. Both
    sides cascade, like the tag join tables.
    """

    __tablename__ = "workflow_knowledge_bases"

    workflow_id: str = Field(primary_key=True)
    knowledge_base_id: str = Field(primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_knowledge_bases_workflow_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name="fk_workflow_knowledge_bases_knowledge_base_id",
            ondelete="CASCADE",
        ),
        Index("ix_workflow_knowledge_bases_knowledge_base_id", "knowledge_base_id"),
    )


class KnowledgeBaseIdsUpdate(SQLModel):
    """Request body for ``PUT /workflows/{id}/knowledge-bases``: the full link set."""

    model_config = _alias_config
    knowledge_base_ids: list[str] = Field(
        default=[], max_length=MAX_WORKFLOW_KNOWLEDGE_BASES
    )

    @field_validator("knowledge_base_ids")
    @classmethod
    def _dedupe(cls, ids: list[str]) -> list[str]:
        """Drop duplicate ids while preserving their first-seen order."""
        return list(dict.fromkeys(ids))
