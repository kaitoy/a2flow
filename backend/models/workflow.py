from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowUpdate(SQLModel):
    model_config = _alias_config
    name: str | None = None
    prompt: str | None = None
    description: str | None = None
    agent_skill_id: str | None = None


class WorkflowCreate(SQLModel):
    model_config = _alias_config
    name: str
    prompt: str
    description: str | None = None
    agent_skill_id: str


class Workflow(WorkflowCreate, BaseEntity, table=True):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("name", name="uq_workflows_name"),
        Index("ix_workflows_name", "name"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )
