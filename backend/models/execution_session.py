"""ExecutionSession: one ADK session taking part in a WorkflowExecution.

A run starts with a single **main session** -- the workflow session named by
:attr:`models.workflow_execution.WorkflowExecution.session_id`, whose row here
shares that id. When the run's task graph branches, further **branch sessions**
are forked from an existing one (``parent_id``) so independent branches can be
worked in parallel; each is its own ADK session and its own row.

Which session works a task is recorded on the task itself
(:attr:`models.workflow_task.WorkflowTask.session_id`): the server assigns
tasks to sessions (:mod:`services.execution_branching`), and a session may only
advance the tasks assigned to it.
"""

from enum import StrEnum

from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field

from models.base import BaseEntity
from models.tenant_scoped import TenantScoped


class ExecutionSessionStatus(StrEnum):
    """Lifecycle states of an ExecutionSession, declared in sort order."""

    idle = "idle"
    """Alive, and not currently running a turn."""

    done = "done"
    """A branch session with nothing left assigned to it; it never resumes."""


class ExecutionSession(TenantScoped, BaseEntity, table=True):
    """Database-persisted ADK session of a WorkflowExecution.

    ``id`` *is* the ADK session id rather than a surrogate key, so an agent tool
    holding only ``tool_context.session.id`` can find its row directly
    (:func:`repositories.tenant_bootstrap.resolve_workflow_execution_tenant`).
    Rows cascade-delete with their execution; ``parent_id`` is ``NULL`` for the
    main session and names the session a branch was forked from otherwise.
    """

    __tablename__ = "execution_sessions"
    __table_args__ = (
        Index("ix_execution_sessions_workflow_execution_id", "workflow_execution_id"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_execution_sessions_workflow_execution_id",
        ),
        ForeignKeyConstraint(
            ["parent_id"],
            ["execution_sessions.id"],
            ondelete="CASCADE",
            name="fk_execution_sessions_parent_id",
        ),
    )

    workflow_execution_id: str
    parent_id: str | None = None
    status: ExecutionSessionStatus = Field(default=ExecutionSessionStatus.idle)
