"""WorkflowSession data models representing a running instance of a workflow."""

from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel

from models.base import BaseEntity


class WorkflowSessionCreate(SQLModel):
    """Snapshot of workflow and skill metadata recorded when a workflow is executed."""

    session_id: str
    workflow_name: str
    workflow_prompt: str
    workflow_description: str | None = None
    agent_skill_id: str
    agent_skill_name: str
    agent_skill_repo_url: str
    agent_skill_repo_path: str
    skill_dir: str
    user_id: str


class WorkflowSession(WorkflowSessionCreate, BaseEntity, table=True):
    """Database-persisted record linking an ADK session to the workflow that created it."""

    __tablename__ = "workflow_sessions"
    workflow_id: str | None = None
    __table_args__ = (
        Index("ix_workflow_sessions_session_id", "session_id"),
        ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
    )
