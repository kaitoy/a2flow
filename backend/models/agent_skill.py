from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class AgentSkillUpdate(SQLModel):
    model_config = _alias_config
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    description: str | None = None


class AgentSkillCreate(AgentSkillUpdate):
    name: str
    repo_url: str
    repo_path: str = ""


class AgentSkill(AgentSkillCreate, BaseEntity, table=True):
    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agent_skills_name"),
        Index("ix_agent_skills_name", "name"),
    )
