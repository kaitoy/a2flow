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
from typing import Any

from sqlalchemy import Column, ForeignKeyConstraint, Index
from sqlmodel import Field

from models.base import BaseEntity, JSONColumn
from models.tenant_scoped import TenantScoped


class ExecutionSessionStatus(StrEnum):
    """Lifecycle states of an ExecutionSession, declared in sort order."""

    queued = "queued"
    """Holds input the server has yet to run a turn on."""

    running = "running"
    """A server-driven turn is under way (or its process died mid-turn)."""

    waiting_for_input = "waiting_for_input"
    """Paused on a form (``render_a2ui``) someone has to fill in."""

    waiting_for_approval = "waiting_for_approval"
    """Paused on an approval (``render_approval``) someone has to decide."""

    idle = "idle"
    """Alive, with nothing to run and nothing pending."""

    done = "done"
    """Finished for good: a branch with nothing left assigned, or a finished run."""

    error = "error"
    """Its last turn failed; the next input queues it again."""


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
    #: The input the next server-driven turn runs on, as a
    #: :class:`services.session_inputs.SessionInput` dump: at most one, since a
    #: session holding unrun input is ``queued`` and accepts no more.
    pending_input: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONColumn, nullable=True)
    )
    #: The client-tool calls the last turn left unanswered, each
    #: ``{"tool_call_id", "name", "approval_id"}`` -- what resuming has to answer.
    waiting_on: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
