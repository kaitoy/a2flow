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

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import field_serializer, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, ForeignKeyConstraint, Index, Text
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z_or_none
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


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

    scheduled = "scheduled"
    """Paused until ``resume_at``, the time its agent chose with ``wait_until``."""

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
    #: The AG-UI run id of the turn under way, or ``None`` between turns. While
    #: set, a history read stops at ``run_event_index`` and the rest of the turn
    #: is replayed from its :class:`SessionStreamEvent` rows instead, so a
    #: viewer joining mid-turn sees it once, not twice.
    active_run_id: str | None = None
    #: How many ADK events the session held when the active turn started.
    run_event_index: int = Field(default=0)
    #: For a branch session, how many of its leading ADK events were copied from
    #: the session it was forked from: the context it started with, which its
    #: own chat does not show again. ``0`` for the main session, and for a
    #: branch whose first turn has not run yet.
    fork_event_count: int = Field(default=0)
    #: What a finished branch session reported last -- handed to the main
    #: session when it picks up the join the branch fed.
    summary: str | None = Field(default=None, sa_type=Text)
    #: When a ``scheduled`` session is due to run again. Set by the agent's
    #: ``wait_until`` tool during a turn, kept while the session is
    #: ``scheduled``, and cleared by any other state or by queued input.
    resume_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    @field_serializer("resume_at", when_used="json")
    def _serialize_resume_at(self, dt: datetime | None) -> str | None:
        """Serialize ``resume_at`` as ISO-8601 with a ``Z`` suffix, or ``None``."""
        return iso_z_or_none(dt)


class SessionHistory(SQLModel):
    """One session's chat history, and the cursor to stream what follows from.

    Attributes:
        messages: The AG-UI messages, oldest first, with sender and task
            attribution merged in.
        stream_cursor: The id of the last streamed event the history already
            covers; a viewer subscribes to the session's stream after it.
        running: Whether a turn is queued or under way, so a viewer can show
            the agent working before the turn's first streamed event.
    """

    model_config = _alias_config
    messages: list[dict[str, Any]]
    stream_cursor: int
    running: bool = False


class A2uiActionInput(SQLModel):
    """The answer to a form (``render_a2ui`` surface) a session is paused on.

    Attributes:
        tool_call_id: The paused ``render_a2ui`` call the form came from.
        content: The tool result: the action taken and the values entered, as
            the frontend formats them.
    """

    model_config = _alias_config
    tool_call_id: str = Field(min_length=1)
    content: str = Field(max_length=100_000)


class SessionInputCreate(SQLModel):
    """What a person sends to a session: a chat message, or a form's answer.

    Exactly one of the two. An approval is not decided here -- that is
    ``PATCH /approvals/{id}``, which resumes the session itself.
    """

    model_config = _alias_config
    message: str | None = Field(default=None, max_length=100_000)
    #: Aliased by hand: the generator would spell it ``a2UiAction``.
    a2ui_action: A2uiActionInput | None = Field(default=None, alias="a2uiAction")

    @model_validator(mode="after")
    def _exactly_one(self) -> "SessionInputCreate":
        """Reject a body carrying both a message and a form answer, or neither."""
        if (self.message is None) == (self.a2ui_action is None):
            raise ValueError("send exactly one of message or a2uiAction")
        return self


class SessionStreamEvent(SQLModel, table=True):
    """One AG-UI event of a session's current turn, as streamed to its viewers.

    The turn runs in whichever process picked it up, while the people watching
    the session may be connected to any replica; this table is how the events
    reach them. Rows are appended in order by the one process holding the
    session's run lock, so ``id`` orders a session's events, and a viewer
    resumes from the last id it saw. A new turn deletes the previous turn's
    rows: once a turn has ended, its events are in the session's history.

    Not tenant scoped on its own: it is only ever read through a session the
    caller was first authorized for, the way a task's dependency edges are.
    """

    __tablename__ = "session_stream_events"
    __table_args__ = (
        Index("ix_session_stream_events_session_id_id", "session_id", "id"),
        ForeignKeyConstraint(
            ["session_id"],
            ["execution_sessions.id"],
            ondelete="CASCADE",
            name="fk_session_stream_events_session_id",
        ),
        # Ids are viewers' cursors, so they must never go backwards. A plain
        # SQLite rowid is max(id) + 1, which falls back once a new turn deletes
        # the previous turn's rows -- leaving a viewer waiting "after" an id the
        # new turn's events never reach. PostgreSQL sequences never reuse ids.
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    run_id: str
    payload: dict[str, Any] = Field(sa_column=Column(JSONColumn, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_type=TZDateTime
    )
