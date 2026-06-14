"""WorkflowTask data models for create, update, read, and database persistence.

A WorkflowTask represents a single actionable item belonging to a WorkflowSession.
Tasks are intended to capture the steps produced by the agent under the workflow
instruction "use the provided skill to produce an actionable task list".

Tasks form a directed acyclic graph (DAG) rather than a flat sequence: each task
may depend on zero or more other tasks in the same session. Dependency edges are
stored in the :class:`WorkflowTaskDependency` join table and surfaced on read
models as ``depends_on_ids``. The ``position`` field is retained purely for
layout/ordering and no longer implies execution order.

A task may also have MCP tools bound to it: each binding names a registered
:class:`models.mcp_server.MCPServer` and one tool on that server. Bindings are
stored in the :class:`WorkflowTaskToolBinding` join table and surfaced on read
models as ``tool_bindings``; at execution time the agent may only invoke MCP
tools bound to the task currently in progress (enforced by ``call_mcp_tool`` in
:mod:`infrastructure.mcp_tools`).
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, Position, ShortText, ToolName

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowTaskStatus(StrEnum):
    """Lifecycle states a WorkflowTask can occupy."""

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class ToolBinding(SQLModel):
    """One MCP tool bound to a WorkflowTask: which server and which tool name."""

    model_config = _alias_config
    mcp_server_id: str
    tool_name: ToolName


class WorkflowTaskUpdate(SQLModel):
    """Partial update payload for a WorkflowTask — every field is optional.

    Does not include ``workflow_session_id``: tasks cannot be re-parented to a
    different session after creation. When ``depends_on_ids`` is ``None`` the
    task's dependency edges are left unchanged; when it is an explicit list the
    full set of edges is replaced with that list. ``tool_bindings`` follows the
    same semantics for the task's bound MCP tools.
    """

    model_config = _alias_config
    title: ShortText | None = None
    description: DescText | None = None
    status: WorkflowTaskStatus | None = None
    position: Position | None = None
    depends_on_ids: list[str] | None = None
    tool_bindings: list[ToolBinding] | None = None


class WorkflowTaskCreate(WorkflowTaskUpdate):
    """Creation payload for a WorkflowTask.

    Inherits the optional fields from :class:`WorkflowTaskUpdate` and tightens
    ``title`` to required, supplies defaults for ``status`` and ``position``,
    adds the required parent ``workflow_session_id`` foreign key, and defaults
    ``depends_on_ids`` and ``tool_bindings`` to empty lists.
    """

    workflow_session_id: str
    title: ShortText
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    position: Position = 0
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowTask(BaseEntity, table=True):
    """Database-persisted WorkflowTask record belonging to a WorkflowSession.

    This table holds only the scalar fields of a task. Dependency edges between
    tasks live in :class:`WorkflowTaskDependency`; they are not columns here.
    """

    __tablename__ = "workflow_tasks"
    __table_args__ = (
        Index("ix_workflow_tasks_session_id", "workflow_session_id"),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
        ),
    )

    workflow_session_id: str
    title: str
    description: str | None = None
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    position: int = 0


class WorkflowTaskRead(BaseEntity):
    """Read model returned by the API, including resolved dependency edges.

    Mirrors the persisted scalar fields of :class:`WorkflowTask` and adds
    ``depends_on_ids``, the list of task IDs this task depends on (each of which
    must precede this task in the DAG), and ``tool_bindings``, the MCP tools
    bound to this task.
    """

    workflow_session_id: str
    title: str
    description: str | None = None
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    position: int = 0
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowTaskDependency(SQLModel, table=True):
    """Directed dependency edge between two WorkflowTasks within a session.

    A row ``(task_id=T, depends_on_id=D)`` means task ``T`` depends on task
    ``D`` — that is, ``D`` must precede ``T``. Edges are required to form a DAG;
    cycles are rejected by the repository before insertion. Both endpoints
    cascade-delete with their tasks, and a check constraint forbids self-loops.
    """

    __tablename__ = "workflow_task_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id"],
            ["workflow_tasks.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["depends_on_id"],
            ["workflow_tasks.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "task_id <> depends_on_id",
            name="ck_workflow_task_dependency_no_self_loop",
        ),
        Index("ix_workflow_task_dependencies_depends_on_id", "depends_on_id"),
    )

    task_id: str = Field(primary_key=True)
    depends_on_id: str = Field(primary_key=True)


class WorkflowTaskToolBinding(SQLModel, table=True):
    """Join row binding one MCP tool to a WorkflowTask.

    A row ``(task_id=T, mcp_server_id=S, tool_name=N)`` means task ``T`` may
    invoke tool ``N`` on registered server ``S`` while it is in progress.
    Bindings cascade-delete with their task; the server side is ``RESTRICT`` so
    a registered server cannot be deleted while tasks still bind its tools.
    """

    __tablename__ = "workflow_task_tool_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id"],
            ["workflow_tasks.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["mcp_server_id"],
            ["mcp_servers.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_workflow_task_tool_bindings_mcp_server_id", "mcp_server_id"),
    )

    task_id: str = Field(primary_key=True)
    mcp_server_id: str = Field(primary_key=True)
    tool_name: str = Field(primary_key=True)
