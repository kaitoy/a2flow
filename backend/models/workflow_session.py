"""WorkflowSession data models representing a running instance of a workflow."""

from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel

from models.base import BaseEntity


class WorkflowSessionCreate(SQLModel):
    """Snapshot of workflow and skill metadata recorded when a workflow is executed.

    ``agent_skill_commit_sha`` pins the run to the skill revision that was
    published when it started, so a later ``pull`` of that skill cannot swap the
    code out from under a conversation already in progress. It names a revision
    directory under ``Settings.skills_dir``, which every replica shares — unlike
    the absolute local path this field replaced, it resolves the same way on
    whichever replica happens to serve the next agent run.

    It is nullable because rows created before the revisioned skill store
    existed have no revision to name; those fall back to the skill's current
    ``commit_sha`` (see ``WorkflowSessionService.resolve_agent``).
    """

    session_id: str
    workflow_name: str
    workflow_prompt: str
    workflow_description: str | None = None
    agent_skill_id: str
    agent_skill_name: str
    agent_skill_repo_url: str
    agent_skill_repo_path: str
    agent_skill_commit_sha: str | None = None
    user_id: str


class WorkflowSession(WorkflowSessionCreate, BaseEntity, table=True):
    """Database-persisted record linking an ADK session to the workflow that created it."""

    __tablename__ = "workflow_sessions"
    workflow_id: str | None = None
    __table_args__ = (
        Index("ix_workflow_sessions_session_id", "session_id"),
        ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
    )
