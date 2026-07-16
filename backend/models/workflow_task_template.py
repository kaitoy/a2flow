"""WorkflowTaskTemplate data models for create, update, read, and persistence.

A WorkflowTaskTemplate is one step of a Workflow's pre-planned task list. The
templates are produced by the workflow's planning session (the agent registers
them via the planning tools) and may also be edited manually through the admin
API. When the workflow is executed, its templates are copied into status-ful
:class:`models.workflow_task.WorkflowTask` rows belonging to the new
WorkflowSession, so later template edits never affect runs already started.

Like session tasks, templates form a directed acyclic graph (DAG): dependency
edges live in :class:`WorkflowTaskTemplateDependency` and are surfaced on read
models as ``depends_on_ids``. ``position`` is retained purely for layout and
implies no execution order. MCP tool bindings live in
:class:`WorkflowTaskTemplateToolBinding` and are surfaced as ``tool_bindings``;
they are copied onto the run's tasks at execute time. Templates carry no
``status`` — status is a property of a run, not of the plan.
"""

from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, Position, ShortText
from models.workflow_task import ToolBinding

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowTaskTemplateUpdate(SQLModel):
    """Partial update payload for a WorkflowTaskTemplate — every field is optional.

    Does not include ``workflow_id``: templates cannot be re-parented to a
    different workflow after creation. When ``depends_on_ids`` is ``None`` the
    template's dependency edges are left unchanged; when it is an explicit list
    the full set of edges is replaced with that list. ``tool_bindings`` follows
    the same semantics for the template's bound MCP tools.
    """

    model_config = _alias_config
    title: ShortText | None = None
    description: DescText | None = None
    position: Position | None = None
    depends_on_ids: list[str] | None = None
    tool_bindings: list[ToolBinding] | None = None


class WorkflowTaskTemplateCreate(WorkflowTaskTemplateUpdate):
    """Creation payload for a WorkflowTaskTemplate.

    Inherits the optional fields from :class:`WorkflowTaskTemplateUpdate`,
    tightens ``title`` to required, supplies a default ``position``, adds the
    required parent ``workflow_id`` foreign key, and defaults
    ``depends_on_ids`` and ``tool_bindings`` to empty lists.
    """

    workflow_id: str
    title: ShortText
    position: Position = 0
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowTaskTemplate(BaseEntity, table=True):
    """Database-persisted WorkflowTaskTemplate record belonging to a Workflow.

    This table holds only the scalar fields of a template. Dependency edges
    live in :class:`WorkflowTaskTemplateDependency`; they are not columns here.
    """

    __tablename__ = "workflow_task_templates"
    __table_args__ = (
        Index("ix_workflow_task_templates_workflow_id", "workflow_id"),
        ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            ondelete="CASCADE",
        ),
    )

    workflow_id: str
    title: str
    description: str | None = None
    position: int = 0


class WorkflowTaskTemplateRead(BaseEntity):
    """Read model returned by the API, including resolved dependency edges.

    Mirrors the persisted scalar fields of :class:`WorkflowTaskTemplate` and
    adds ``depends_on_ids``, the list of template IDs this template depends on,
    and ``tool_bindings``, the MCP tools bound to this template.
    """

    workflow_id: str
    title: str
    description: str | None = None
    position: int = 0
    depends_on_ids: list[str] = []
    tool_bindings: list[ToolBinding] = []


class WorkflowTaskTemplateDependency(SQLModel, table=True):
    """Directed dependency edge between two WorkflowTaskTemplates of a workflow.

    A row ``(template_id=T, depends_on_id=D)`` means template ``T`` depends on
    template ``D`` — that is, ``D`` must precede ``T``. Edges are required to
    form a DAG; cycles are rejected by the repository before insertion. Both
    endpoints cascade-delete with their templates, and a check constraint
    forbids self-loops.
    """

    __tablename__ = "workflow_task_template_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id"],
            ["workflow_task_templates.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["depends_on_id"],
            ["workflow_task_templates.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "template_id <> depends_on_id",
            name="ck_workflow_task_template_dependency_no_self_loop",
        ),
        Index("ix_workflow_task_template_dependencies_depends_on_id", "depends_on_id"),
    )

    template_id: str = Field(primary_key=True)
    depends_on_id: str = Field(primary_key=True)


class WorkflowTaskTemplateToolBinding(SQLModel, table=True):
    """Join row binding one MCP tool to a WorkflowTaskTemplate.

    A row ``(template_id=T, mcp_server_id=S, tool_name=N)`` means the task
    copied from template ``T`` may invoke tool ``N`` on registered server ``S``
    while it is in progress. Bindings cascade-delete with their template; the
    server side is ``RESTRICT`` so a registered server cannot be deleted while
    templates still bind its tools.
    """

    __tablename__ = "workflow_task_template_tool_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["template_id"],
            ["workflow_task_templates.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["mcp_server_id"],
            ["mcp_servers.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_workflow_task_template_tool_bindings_mcp_server_id", "mcp_server_id"),
    )

    template_id: str = Field(primary_key=True)
    mcp_server_id: str = Field(primary_key=True)
    tool_name: str = Field(primary_key=True)
