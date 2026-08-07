"""WorkflowExecution data models representing one run of a published workflow.

A WorkflowExecution records the run itself: the workflow and skill metadata
snapshotted when it started, and the parent of the WorkflowTasks, Approvals,
and MessageMeta rows the run produces.

The chat the run happens in is its **workflow session** — the ADK session named
by :attr:`WorkflowExecutionCreate.session_id`. It is the run-time counterpart of
a *design session*, the chat a workflow is designed in
(:class:`models.workflow.Workflow`). Neither has a table of its own: a workflow
session exists one-to-one with its execution, so the execution's id identifies
it, exactly as a workflow's id identifies its design session.
"""

from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel

from models.base import BaseEntity
from models.tenant_scoped import TenantScoped


class WorkflowExecutionCreate(SQLModel):
    """Snapshot of workflow and skill metadata recorded when a workflow is executed.

    ``agent_skill_commit_sha`` pins the run to the skill revision that was
    published when it started, so a later ``pull`` of that skill cannot swap the
    code out from under a conversation already in progress. It names a revision
    directory under ``Settings.skills_dir``, which every replica shares — unlike
    the absolute local path this field replaced, it resolves the same way on
    whichever replica happens to serve the next agent run.

    It is nullable because rows created before the revisioned skill store
    existed have no revision to name; those fall back to the skill's current
    ``commit_sha`` (see ``WorkflowExecutionService.resolve_agent``).
    """

    session_id: str
    """ADK/AG-UI id of this execution's workflow session — the chat it runs in."""

    name: str
    description: str | None = None
    agent_skill_id: str
    agent_skill_name: str
    agent_skill_repo_url: str
    agent_skill_repo_path: str
    agent_skill_commit_sha: str | None = None
    initiator_id: str


class WorkflowExecution(WorkflowExecutionCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted run record, linking its workflow session to the workflow.

    ``workflow_id`` is nullable and ``SET NULL`` on delete: the snapshot columns
    keep the run readable after its workflow design is gone. ``session_id`` is
    indexed so agent tools can map the workflow session they run in back to this
    record.
    """

    __tablename__ = "workflow_executions"
    workflow_id: str | None = None
    __table_args__ = (
        Index("ix_workflow_executions_session_id", "session_id"),
        ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
    )
