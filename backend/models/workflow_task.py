"""WorkflowTask data models for create, update, read, and database persistence.

A WorkflowTask represents a single actionable item belonging to a WorkflowExecution.
Tasks are intended to capture the steps produced by the agent under the workflow
instruction "use the provided skill to produce an actionable task list".

Tasks form a directed acyclic graph (DAG) rather than a flat sequence: each task
may depend on zero or more other tasks in the same session. Dependency edges are
stored in the :class:`WorkflowTaskDependency` join table and surfaced on read
models as ``depends_on_ids``. Tasks are listed in ``created_at`` order; there is
no separate layout/ordering field.

A task may also have MCP tools bound to it: each binding names a registered
:class:`models.mcp_server.MCPServer` and one tool on that server. Bindings are
stored in the :class:`WorkflowTaskToolBinding` join table and surfaced on read
models as ``tool_bindings``; at execution time the agent may only invoke MCP
tools bound to the task currently in progress (enforced by ``call_mcp_tool`` in
:mod:`infrastructure.mcp_tools`). A binding also carries
``requires_input_approval``, which says whether an approval covering the task
must bound the arguments this tool is called with -- see :class:`ToolBinding`.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, ShortText, ToolName
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowTaskStatus(StrEnum):
    """Lifecycle states a WorkflowTask can occupy."""

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class TaskErrorKind(StrEnum):
    """Why a WorkflowTask failed, as a small closed set of causes.

    Recorded alongside ``status="failed"`` so the failed runs can be triaged by
    cause instead of read one by one: it is the ``error_kind`` label on the
    failed-task metric and the grouping key of the "needs attention" list
    (``GET /workflow-executions/failures``).

    The set is deliberately coarse. It is filled in by the agent through
    ``update_workflow_task`` (``infrastructure/workflow_task_tools.py``), whose
    argument documentation spells out every member, so each value has to be
    distinguishable by a model reading a tool error at run time. Anything
    finer-grained belongs in the free-text ``error_message``.
    """

    api_error = "api_error"
    """An external API or MCP tool returned an error response."""

    timeout = "timeout"
    """A call did not return within its time limit."""

    script_error = "script_error"
    """The skill's own code raised an unhandled exception."""

    invalid_input = "invalid_input"
    """The data the task was given was malformed or incomplete."""

    permission_denied = "permission_denied"
    """The run lacked the credentials or authorization to proceed."""

    rejected = "rejected"
    """A human rejected the task's approval request, so it could not continue."""

    other = "other"
    """None of the above; see ``error_message``."""


class ToolBinding(SQLModel):
    """One MCP tool bound to a WorkflowTask: which server and which tool name.

    ``requires_input_approval`` is the design-time answer to "must a human agree
    to the values this tool is called with?". It defaults to ``True``, which is
    the rule an approval-covered task is held to: every call the approval
    authorizes is declared argument by argument and matched against that
    declaration (:mod:`infrastructure.approved_calls`).

    Clearing it exempts the tool from that matching alone -- **not** from the
    approval. A covered task still calls nothing until its approval is granted;
    what changes is that once it is, this tool may be called with any arguments.
    It is meant for a tool that only reads: there is no consequence for an
    approver to weigh, and an agent exploring with it cannot know its arguments
    at the moment the request is made, so demanding a declaration would only
    produce a dishonest one.

    The flag is set on the workflow's task templates and copied onto a run's
    tasks at execute time. A run cannot set it: the execution agent may change
    only a task's ``status`` (:func:`infrastructure.workflow_task_tools.update_workflow_task`),
    and :meth:`services.workflow_task.WorkflowTaskService._assert_tool_bindings_change_allowed`
    refuses to change the bindings of a task an approval covers.
    """

    model_config = _alias_config
    mcp_server_id: str
    tool_name: ToolName
    #: Whether a call to this tool must fit the approver's declaration. ``False``
    #: exempts its arguments from that check; the approval itself still applies.
    requires_input_approval: bool = True


class WorkflowTaskUpdate(SQLModel):
    """Partial update payload for a WorkflowTask — every field is optional.

    Does not include ``workflow_execution_id``: tasks cannot be re-parented to a
    different session after creation. When ``depends_on_ids`` is ``None`` the
    task's dependency edges are left unchanged; when it is an explicit list the
    full set of edges is replaced with that list. ``tool_bindings`` follows the
    same semantics for the task's bound MCP tools.

    ``error_kind`` and ``error_message`` describe why a task failed and are
    meaningful only alongside ``status="failed"``. They are not enforced to
    travel together with that status — a caller may record the cause in a
    follow-up write — but neither is cleared automatically, so a task moved back
    out of ``failed`` should pass them explicitly as ``None``.
    """

    model_config = _alias_config
    title: ShortText | None = None
    description: DescText | None = None
    status: WorkflowTaskStatus | None = None
    error_kind: TaskErrorKind | None = None
    error_message: ShortText | None = None
    depends_on_ids: list[str] | None = None
    tool_bindings: list[ToolBinding] | None = None


class WorkflowTaskCreate(WorkflowTaskUpdate):
    """Creation payload for a WorkflowTask.

    Inherits the optional fields from :class:`WorkflowTaskUpdate` and tightens
    ``title`` to required, supplies a default for ``status``, adds the required
    parent ``workflow_execution_id`` foreign key, and defaults
    ``depends_on_ids`` and ``tool_bindings`` to empty lists.
    """

    workflow_execution_id: str
    title: ShortText
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowTask(TenantScoped, BaseEntity, table=True):
    """Database-persisted WorkflowTask record belonging to a WorkflowExecution.

    This table holds only the scalar fields of a task. Dependency edges between
    tasks live in :class:`WorkflowTaskDependency`; they are not columns here.
    """

    __tablename__ = "workflow_tasks"
    __table_args__ = (
        Index("ix_workflow_tasks_workflow_execution_id", "workflow_execution_id"),
        Index("ix_workflow_tasks_tenant_id_status", "tenant_id", "status"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
        ),
    )

    workflow_execution_id: str
    title: str
    description: str | None = None
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    error_kind: TaskErrorKind | None = None
    error_message: str | None = None


class WorkflowTaskRead(BaseEntity):
    """Read model returned by the API, including resolved dependency edges.

    Mirrors the persisted scalar fields of :class:`WorkflowTask` and adds
    ``depends_on_ids``, the list of task IDs this task depends on (each of which
    must precede this task in the DAG), and ``tool_bindings``, the MCP tools
    bound to this task.

    ``error_kind`` / ``error_message`` are carried here as well as on the table
    class, which is what makes them filterable and sortable through the list
    endpoints: ``repositories/workflow_task.py`` passes this class as the
    ``readable`` schema, and a field only resolves when present on both.
    """

    workflow_execution_id: str
    title: str
    description: str | None = None
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    error_kind: TaskErrorKind | None = None
    error_message: str | None = None
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

    ``requires_input_approval`` is not part of the key: it describes the one
    binding the key already identifies. See :class:`ToolBinding` for what it
    means.
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
    requires_input_approval: bool = Field(default=True)
