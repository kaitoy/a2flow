from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class AgentSkillUpdate(SQLModel):
    name: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    description: str | None = None


class AgentSkillCreate(AgentSkillUpdate):
    name: str
    repo_url: str
    repo_path: str = ""


class AgentSkill(AgentSkillCreate, table=True):
    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agent_skills_name"),
        Index("ix_agent_skills_name", "name"),
    )
    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="")
    updated_by: str = Field(default="")
