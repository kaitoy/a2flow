from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import SQLModel

from models.base import AuditedBase


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


class Workflow(WorkflowCreate, AuditedBase, table=True):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("name", name="uq_workflows_name"),
        Index("ix_workflows_name", "name"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )
