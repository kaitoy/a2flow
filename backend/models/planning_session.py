"""PlanningSession data models representing a workflow's planning chat.

A PlanningSession is the chat in which a Workflow's task templates are
produced and refined. Exactly one exists per workflow: it is created together
with the draft workflow by the generation flow, its first exchange is driven
by a background agent run, and the user can reopen it later to adjust the
templates conversationally. It is deliberately a separate entity from
:class:`models.workflow_session.WorkflowSession`, which represents a run of a
published workflow.
"""

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import SQLModel

from models.base import BaseEntity


class PlanningSessionCreate(SQLModel):
    """Creation payload recorded when a workflow's planning session is opened.

    ``agent_skill_commit_sha`` pins the session to the skill revision that was
    published when generation started, so a later ``pull`` of the skill cannot
    swap the planning agent's code mid-conversation. Generation requires a
    published revision, so unlike WorkflowSession the pin is always present.
    """

    session_id: str
    workflow_id: str
    agent_skill_id: str
    agent_skill_commit_sha: str
    user_id: str


class PlanningSession(PlanningSessionCreate, BaseEntity, table=True):
    """Database-persisted record linking an ADK chat session to its workflow.

    ``workflow_id`` is unique — a workflow has exactly one planning session —
    and cascade-deletes with the workflow. ``session_id`` is the ADK/AG-UI
    thread id, indexed so agent tools can map the session they run in back to
    this record (and through it to the workflow whose templates they edit).
    """

    __tablename__ = "planning_sessions"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_planning_sessions_workflow_id"),
        Index("ix_planning_sessions_session_id", "session_id"),
        ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )
