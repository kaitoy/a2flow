"""Workflow data models for update, generation, and database persistence.

A Workflow is a reusable, pre-planned unit of work: an agent skill plus the
task templates generated for it by a planning session. Workflows are never
created directly through a plain POST — they are born from
``POST /agent-skills/{skill_id}/workflows`` ("Generate workflow"), which
registers a draft row and schedules a background planning run that fills in
the task templates and the conversation summary (``description``).
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, EntityName, PromptText
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowStatus(StrEnum):
    """Lifecycle states a Workflow can occupy.

    Only ``published`` workflows may be executed; every other state rejects
    ``POST /workflows/{id}/execute`` with ``WORKFLOW_NOT_RUNNABLE``.
    """

    generating = "generating"
    """The background planning run that fills in the task templates is in flight."""

    draft = "draft"
    """The initial plan exists (or generation was skipped); not yet executable."""

    failed = "failed"
    """The background planning run failed; ``generation_error`` carries the reason."""

    published = "published"
    """Explicitly published by a developer; executable."""


class WorkflowUpdate(SQLModel):
    """Partial update payload for a Workflow — all fields are optional.

    Only ``name`` and ``description`` are client-writable: the bound skill is
    fixed at generation time (the task templates were planned against it), and
    ``status`` is server-managed via generation and publish.
    """

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None


class WorkflowCreate(WorkflowUpdate):
    """Creation payload for a Workflow with required fields.

    Not exposed as a POST body — workflows are created internally by the
    generation flow (``WorkflowGenerationService``), which supplies the skill.
    """

    name: EntityName
    agent_skill_id: str


class Workflow(WorkflowCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted workflow binding task templates to an agent skill.

    ``status`` and ``generation_error`` are server-managed: they are declared
    on the table class only, so they are absent from ``WorkflowCreate`` /
    ``WorkflowUpdate`` and cannot be written through the API. They are set by
    the generation background job (``services/workflow_generation.py``) and by
    ``POST /workflows/{id}/publish``.
    """

    __tablename__ = "workflows"

    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    status: WorkflowStatus = Field(default=WorkflowStatus.draft)
    generation_error: str | None = None

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_id_name"),
        Index("ix_workflows_tenant_id_name", "tenant_id", "name"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )


class GenerateWorkflowRequest(SQLModel):
    """Request body of ``POST /agent-skills/{skill_id}/workflows``.

    ``name`` becomes the new workflow's unique name (the UI prefills it with
    the skill name); ``prompt`` is the user's request that the background
    planning run breaks into task templates.
    """

    model_config = _alias_config
    name: EntityName
    prompt: PromptText
