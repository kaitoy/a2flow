from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class WorkflowUpdate(SQLModel):
    name: str | None = None
    prompt: str | None = None
    description: str | None = None
    agent_skill_id: str | None = None


class WorkflowCreate(SQLModel):
    name: str
    prompt: str
    description: str | None = None
    agent_skill_id: str


class Workflow(WorkflowCreate, table=True):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("name", name="uq_workflows_name"),
        Index("ix_workflows_name", "name"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )
    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(default="")
    updated_by: str = Field(default="")
