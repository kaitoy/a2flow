"""Tag data models: the tag master table and the join rows that attach tags to records.

A Tag is a tenant-scoped label that can be attached to a Secret, a Workflow, an
MCPServer, or an AgentSkill. One tag set is shared by all four resource types,
so filtering a list by ``aws`` narrows secrets and MCP servers alike.

Attachment lives in one join table per resource type
(:class:`SecretTag`, :class:`WorkflowTag`, :class:`McpServerTag`,
:class:`AgentSkillTag`), each keyed by the record's id and the tag's **id** —
never its name. That indirection is the point: renaming a tag changes only the
``tags`` row, so every record already carrying it follows along.

Four join tables rather than one polymorphic ``(resource_type, resource_id)``
table, because a polymorphic owner column cannot carry a real foreign key. Every
other join table in this codebase (``user_group_members``,
``workflow_task_template_dependencies``, ``workflow_task_template_tool_bindings``)
declares real constraints, and so do these — which is also what makes
``ondelete="CASCADE"`` clean up attachments when either side disappears.

Tags are **not** a field of the four resources' payload models. Those table
classes inherit their ``...Create`` schema (e.g.
``Secret(SecretCreate, TenantScoped, BaseEntity, table=True)``), so a
``list[str]`` field added there would have to become a column of the resource's
own table — the same constraint documented on
:class:`models.user_group.UserGroup`. Attachment is therefore written through a
sub-resource, ``PUT /{resource}/{id}/tags``, whose body is
:class:`TagIdsUpdate`, and read back through each resource's ``...Read``
projection.
"""

from enum import StrEnum

from pydantic import field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import EntityName
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

MAX_RECORD_TAGS = 50
"""Upper bound on the tags one record may carry in a single write.

Also bounds how many ``?tag=`` values one list request may filter on, since
each one adds an ``EXISTS`` subquery to the statement.
"""


class TagColor(StrEnum):
    """Palette slot a tag's chip is drawn in.

    Stored as the slot name rather than a color value so the palette itself can
    be retuned later without rewriting rows, and so light and dark themes can
    render the same tag differently — a single stored hex could not satisfy
    both. The frontend maps these names to classes in ``src/lib/tag-palette.ts``.
    """

    mint = "mint"
    teal = "teal"
    cyan = "cyan"
    indigo = "indigo"
    violet = "violet"
    rose = "rose"
    amber = "amber"
    slate = "slate"


class TagUpdate(SQLModel):
    """Partial update payload for a Tag — every field is optional.

    ``tenant_id`` is intentionally absent: a tag belongs to the tenant it was
    created in and cannot be moved. ``name`` is free to change at any time;
    attachments reference the tag's id, so renaming never detaches anything.
    """

    model_config = _alias_config
    name: EntityName | None = None
    color: TagColor | None = None


class TagCreate(TagUpdate):
    """Creation payload for a Tag with a required name and a default color."""

    name: EntityName
    color: TagColor = TagColor.slate


class Tag(TagCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted tag: a named, colored label shared by every taggable resource.

    ``name`` is unique within a tenant, so ``tenant_id`` is redeclared without
    its own index and folded into a composite constraint instead.

    Unlike the resources it labels, a tag carries no join-derived field, so the
    table class doubles as the API response model and no ``TagRead`` projection
    is needed.
    """

    __tablename__ = "tags"
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_id_name"),
        Index("ix_tags_tenant_id_name", "tenant_id", "name"),
    )


class TagLink(SQLModel):
    """Mixin contributing the two columns every tag join table shares.

    The owner column is named ``resource_id`` rather than ``secret_id`` /
    ``workflow_id`` / … so :class:`repositories.tags.TagLinks` can work against
    ``type[TagLink]`` and write ``col(link_model.resource_id)`` directly,
    instead of reaching for the column by name through ``getattr`` and losing
    its type. The table name carries the context the column name gives up.

    Subclasses supply ``__tablename__`` and the ``__table_args__`` holding both
    foreign keys and the ``tag_id`` index.
    """

    resource_id: str = Field(primary_key=True)
    tag_id: str = Field(primary_key=True)


def _link_table_args(table: str, owner_table: str) -> tuple[object, ...]:
    """Build the constraints shared by every tag join table.

    Both sides cascade: with the owning record because a label is meaningless
    without the thing it labels, and with the tag because deleting a tag is how
    a user retires it — a ``RESTRICT`` there would make any tag in use
    undeletable. The extra index on ``tag_id`` serves the reverse lookup, since
    the composite primary key only leads with ``resource_id``.

    Args:
        table: Name of the join table, used to name its index.
        owner_table: Name of the table whose rows ``resource_id`` references.

    Returns:
        The ``__table_args__`` tuple for the join table.
    """
    return (
        ForeignKeyConstraint(
            ["resource_id"], [f"{owner_table}.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        Index(f"ix_{table}_tag_id", "tag_id"),
    )


class SecretTag(TagLink, table=True):
    """Join row attaching one Tag to one Secret."""

    __tablename__ = "secret_tags"
    __table_args__ = _link_table_args("secret_tags", "secrets")


class WorkflowTag(TagLink, table=True):
    """Join row attaching one Tag to one Workflow."""

    __tablename__ = "workflow_tags"
    __table_args__ = _link_table_args("workflow_tags", "workflows")


class McpServerTag(TagLink, table=True):
    """Join row attaching one Tag to one MCPServer."""

    __tablename__ = "mcp_server_tags"
    __table_args__ = _link_table_args("mcp_server_tags", "mcp_servers")


class AgentSkillTag(TagLink, table=True):
    """Join row attaching one Tag to one AgentSkill."""

    __tablename__ = "agent_skill_tags"
    __table_args__ = _link_table_args("agent_skill_tags", "agent_skills")


class TagIdsUpdate(SQLModel):
    """Request body for ``PUT /{resource}/{id}/tags``: the record's full tag set.

    Replaces the record's attachments wholesale, which is why this is a ``PUT``
    rather than a ``PATCH``; an empty list detaches every tag. It exists as a
    sub-resource instead of a ``tag_ids`` field on each resource's ``...Update``
    payload because those resources' table classes inherit their ``...Create``
    schema, so the field would have to become a column of the resource's own
    table — see the module docstring.
    """

    model_config = _alias_config
    tag_ids: list[str] = Field(default=[], max_length=MAX_RECORD_TAGS)

    @field_validator("tag_ids")
    @classmethod
    def _dedupe_tag_ids(cls, tag_ids: list[str]) -> list[str]:
        """Drop duplicate tag ids while preserving their first-seen order.

        Args:
            tag_ids: The submitted tag ids.

        Returns:
            The deduplicated ids.
        """
        return list(dict.fromkeys(tag_ids))
