"""Workflow data models for create, update, and database persistence."""

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, EntityName, PromptText

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowUpdate(SQLModel):
    """Partial update payload for a Workflow — all fields are optional."""

    model_config = _alias_config
    name: EntityName | None = None
    prompt: PromptText | None = None
    description: DescText | None = None
    agent_skill_id: str | None = None


class WorkflowCreate(SQLModel):
    """Creation payload for a Workflow with required fields."""

    model_config = _alias_config
    name: EntityName
    prompt: PromptText
    description: DescText | None = None
    agent_skill_id: str


class Workflow(WorkflowCreate, BaseEntity, table=True):
    """Database-persisted workflow that binds a system prompt to an agent skill."""

    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("name", name="uq_workflows_name"),
        Index("ix_workflows_name", "name"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )
