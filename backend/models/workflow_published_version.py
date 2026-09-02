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

The snapshot is also what a non-``developer`` caller *reads*: while a workflow
is ``modified``, its unpublished edits are visible only to a ``developer``, and
everyone else is served this row projected into the ordinary read models by
:func:`published_workflow_read` and :func:`published_template_read`. Those two
functions are the Python half of that projection; the SQL half — the expressions
that make filtering and sorting agree with what is displayed — lives in
``repositories.workflow.SqlWorkflowRepository.list`` and
``repositories.workflow_published_version.SqlWorkflowPublishedVersionRepository.list_templates``.
Change one half and the other must change with it.
"""

from datetime import datetime
from typing import Any

from pydantic.alias_generators import to_camel
from sqlalchemy import Column, ForeignKeyConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.tenant_scoped import TenantScoped
from models.workflow import Workflow, WorkflowRead, WorkflowStatus
from models.workflow_task import ToolBinding
from models.workflow_task_template import WorkflowTaskTemplateRead

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowPublishedVersionTemplate(SQLModel):
    """One task template as captured in a published version.

    Mirrors the fields of
    :class:`models.workflow_task_template.WorkflowTaskTemplateRead` that
    describe the design, plus its audit columns: ``id`` is kept so the
    dependency edges in ``depends_on_ids`` stay resolvable within the snapshot
    (and so restoring a snapshot can reuse the original template IDs), and the
    audit columns are kept so the snapshot can be served to a non-``developer``
    through the ordinary read model (see :func:`published_template_read`).

    The audit columns are optional because a snapshot written before they were
    captured must still parse; :func:`published_template_read` falls back to
    the workflow's own audit values for those.
    """

    model_config = _alias_config
    id: str
    title: str
    description: str | None = None
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None


class WorkflowPublishedVersion(TenantScoped, BaseEntity, table=True):
    """Database-persisted snapshot of the last published state of a Workflow.

    Not exposed through the API as a resource of its own: the row is read only
    by :class:`services.workflow.WorkflowService` and
    :class:`services.workflow_task_template.WorkflowTaskTemplateService`, which
    project it into the ordinary ``Workflow`` / ``WorkflowTaskTemplate`` read
    models. The row is replaced on every publish and cascade-deleted with its
    workflow.
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
        The design-describing fields of ``template``, with its audit columns.
    """
    return WorkflowPublishedVersionTemplate(
        id=template.id,
        title=template.title,
        description=template.description,
        depends_on_ids=list(template.depends_on_ids),
        tool_bindings=list(template.tool_bindings),
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by=template.created_by,
        updated_by=template.updated_by,
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


def published_template_read(
    template: WorkflowPublishedVersionTemplate, *, workflow: Workflow
) -> WorkflowTaskTemplateRead:
    """Project a snapshot template into the ordinary task-template read model.

    Lets a non-``developer`` be served the published design through the same
    response shape as the live rows, so no caller has to know which one it got.

    Args:
        template: The snapshot template to project.
        workflow: The workflow the snapshot belongs to, supplying ``workflow_id``
            and the audit values a snapshot written before those were captured
            does not carry.

    Returns:
        The read view of the published template.
    """
    return WorkflowTaskTemplateRead(
        id=template.id,
        workflow_id=workflow.id,
        title=template.title,
        description=template.description,
        depends_on_ids=list(template.depends_on_ids),
        tool_bindings=list(template.tool_bindings),
        created_at=template.created_at or workflow.created_at,
        updated_at=template.updated_at or workflow.updated_at,
        created_by=template.created_by or workflow.created_by,
        updated_by=template.updated_by or workflow.updated_by,
    )


def published_workflow_read(
    workflow: Workflow,
    version: WorkflowPublishedVersion | None,
    *,
    tag_ids: list[str],
) -> WorkflowRead:
    """Project a Workflow as a non-``developer`` caller is allowed to see it.

    A ``modified`` workflow's live row carries edits nobody has approved yet, so
    its name, description, and status are taken from ``version`` instead and the
    status is reported as ``published`` — the workflow's unpublished state is
    not disclosed at all. Every other status already matches its snapshot by
    construction and passes through untouched.

    Never call this for a ``developer``: they are the audience for the live
    values, and go through
    :func:`services.workflow.build_workflow_read` instead.

    Args:
        workflow: The persisted workflow to project.
        version: The workflow's published snapshot, or ``None`` if it has never
            been published. A ``modified`` workflow without one should not
            exist; it is passed through unmasked rather than hidden.
        tag_ids: Ids of the tags attached to ``workflow``.

    Returns:
        The read view of the published design.
    """
    read = WorkflowRead.from_workflow(workflow, tag_ids=tag_ids)
    if workflow.status is not WorkflowStatus.modified or version is None:
        return read
    return read.model_copy(
        update={
            "name": version.name,
            # The snapshot stored the resolved description at publish time, so
            # the generated one it was resolved from has nothing left to add.
            "description": version.description,
            "generated_description": None,
            "status": WorkflowStatus.published,
        }
    )
