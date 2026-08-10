"""Snapshot of a Workflow as it looked the last time it was published.

Publishing a workflow freezes its design: the workflow's name, its summarized
description, and its full task-template list (dependency edges and MCP tool
bindings included) are copied into a
:class:`WorkflowPublishedVersion` row. Editing the workflow afterwards moves it
to :attr:`models.workflow.WorkflowStatus.modified`, and runs started from that
point keep using this snapshot — so the design that was approved by publishing is
the design that executes, until it is published again.

There is at most one row per workflow: each publish replaces the previous
snapshot. The templates are stored as a JSON list rather than as rows of their
own because the snapshot is read and written whole and is never queried by
individual step; :func:`parse_templates` turns them back into typed objects.
"""

from typing import Any

from pydantic.alias_generators import to_camel
from sqlalchemy import Column, ForeignKeyConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.tenant_scoped import TenantScoped
from models.workflow_task import ToolBinding
from models.workflow_task_template import WorkflowTaskTemplateRead

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowPublishedVersionTemplate(SQLModel):
    """One task template as captured in a published version.

    Mirrors the fields of
    :class:`models.workflow_task_template.WorkflowTaskTemplateRead` that
    describe the design, minus the audit columns: ``id`` is kept so the
    dependency edges in ``depends_on_ids`` stay resolvable within the snapshot
    (and so restoring a snapshot can reuse the original template IDs).
    """

    model_config = _alias_config
    id: str
    title: str
    description: str | None = None
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowPublishedVersion(TenantScoped, BaseEntity, table=True):
    """Database-persisted snapshot of the last published state of a Workflow.

    Not exposed through the API: the snapshot is an implementation detail of
    the publish/execute cycle, read only by
    :class:`services.workflow.WorkflowService`. The row is replaced on every
    publish and cascade-deleted with its workflow.
    """

    __tablename__ = "workflow_published_versions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", name="uq_workflow_published_versions_workflow_id"
        ),
        ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            ondelete="CASCADE",
        ),
    )

    workflow_id: str
    name: str
    description: str | None = None
    #: The workflow's task templates at publish time, stored as a JSON list of
    #: :class:`WorkflowPublishedVersionTemplate` payloads (camelCase keys).
    #: Read back through :func:`parse_templates`.
    templates: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )


def snapshot_template(
    template: WorkflowTaskTemplateRead,
) -> WorkflowPublishedVersionTemplate:
    """Capture a live task template as a published-version template.

    Args:
        template: The template read model to capture.

    Returns:
        The design-describing fields of ``template``, without its audit columns.
    """
    return WorkflowPublishedVersionTemplate(
        id=template.id,
        title=template.title,
        description=template.description,
        depends_on_ids=list(template.depends_on_ids),
        tool_bindings=list(template.tool_bindings),
    )


def dump_templates(
    templates: list[WorkflowPublishedVersionTemplate],
) -> list[dict[str, Any]]:
    """Serialize snapshot templates for storage in the JSON column.

    Args:
        templates: The templates to store.

    Returns:
        One camelCase JSON-safe dict per template, in the given order.
    """
    return [t.model_dump(mode="json", by_alias=True) for t in templates]


def parse_templates(
    version: WorkflowPublishedVersion,
) -> list[WorkflowPublishedVersionTemplate]:
    """Restore the typed task templates held by a published version.

    Args:
        version: The snapshot row whose ``templates`` payload to parse.

    Returns:
        The snapshot's templates as typed objects, in stored order.
    """
    return [
        WorkflowPublishedVersionTemplate.model_validate(t) for t in version.templates
    ]
