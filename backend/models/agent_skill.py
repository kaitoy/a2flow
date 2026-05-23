"""AgentSkill data models for create, update, and database persistence."""

from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class AgentSkillUpdate(SQLModel):
    """Partial update payload for an AgentSkill — all fields are optional."""

    model_config = _alias_config
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    description: str | None = None


class AgentSkillCreate(AgentSkillUpdate):
    """Creation payload for an AgentSkill with required fields."""

    name: str
    repo_url: str
    repo_path: str = ""


class AgentSkill(AgentSkillCreate, BaseEntity, table=True):
    """Database-persisted agent skill referencing a Git repository of ADK tools."""

    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agent_skills_name"),
        Index("ix_agent_skills_name", "name"),
    )
