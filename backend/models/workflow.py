"""Workflow data models for update, generation, and database persistence.

A Workflow is a reusable, pre-designed unit of work: an agent skill plus the
task templates generated for it by its design session. Workflows are never
created directly through a plain POST — they are born from
``POST /agent-skills/{skill_id}/workflows`` ("Generate workflow"), which
registers a draft row and schedules a background design run that fills in
the task templates and the first conversation summary
(``generated_description``); later summaries are produced on demand by
``POST /workflows/{id}/generate-description``.

The chat those templates are produced and refined in is the workflow's
**design session** — the ADK session named by :attr:`WorkflowCreate.session_id`
and keyed by the workflow's ``created_by``. It is the design-time counterpart
of a *workflow session*, the chat a run happens in
(:class:`models.workflow_execution.WorkflowExecution`). Neither has a table of
its own: a design session exists one-to-one with its workflow, so the
workflow's id identifies it, exactly as an execution's id identifies its
workflow session. Both are shared chats — a design session by the tenant's
developers, a workflow session by its initiator and approvers — so both record
per-message sender attribution in :class:`models.message_meta.MessageMeta`.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import DescText, EntityName, PromptText
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowStatus(StrEnum):
    """Lifecycle states a Workflow can occupy.

    ``published`` and ``modified`` workflows may be executed by any caller
    holding the ``requester`` or ``developer`` role; ``draft`` workflows may
    additionally be executed, but only by a ``developer`` (or
    ``super_admin``), for pre-publish testing. Every other combination rejects
    ``POST /workflows/{id}/execute`` with ``WORKFLOW_NOT_RUNNABLE`` — see
    :meth:`services.workflow.WorkflowService.execute`.
    """

    generating = "generating"
    """The background design run that fills in the task templates is in flight."""

    draft = "draft"
    """The initial task templates exist (or generation was skipped); not yet executable.

    Also reachable from ``published``/``modified`` via
    ``POST /workflows/{id}/deactivate``, which revokes ``requester`` execute
    access while leaving the task templates and any published snapshot untouched,
    and from ``failed`` by any write to the task templates (see below).
    """

    failed = "failed"
    """The background design run failed; ``generation_error`` carries the reason.

    Not terminal: writing to the task templates — through the design chat's
    agent tools or the admin template editor — recovers the workflow to
    ``draft`` and clears ``generation_error``
    (:meth:`repositories.workflow.SqlWorkflowRepository.mark_design_edited`).
    Rebuilding the design is what repairs a failed design run, and the
    generation job that recorded the failure only runs once, at creation.
    """

    published = "published"
    """Explicitly published by a developer; executable."""

    modified = "modified"
    """Published, then edited: runs still use the last published version.

    Set when a ``published`` workflow's own fields or task templates are saved
    through the API, or when the design agent edits its task templates from
    the workflow's design chat. Execution keeps using the snapshot captured
    at publish time (``models.workflow_published_version.WorkflowPublishedVersion``)
    until the workflow is published again — or the edits are dropped through
    ``POST /workflows/{id}/discard-changes``, which restores the snapshot and
    returns the workflow to ``published``.
    """


class WorkflowUpdate(SQLModel):
    """Partial update payload for a Workflow — all fields are optional.

    ``name`` and ``description`` are client-writable by any ``developer``: the
    bound skill is fixed at generation time (the task templates were designed
    against it), and ``status`` is server-managed via generation and publish.

    ``generated_description`` is also client-writable here, but only by a
    ``super_admin`` — see the guard in
    :meth:`services.workflow.WorkflowService.update`. It holds the AI-produced
    conversation summary; ``description`` is the free-form field a user can
    set to override it. See :attr:`Workflow.effective_description` for how the
    two combine.
    """

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None
    generated_description: DescText | None = None


class WorkflowCreate(WorkflowUpdate):
    """Creation payload for a Workflow with required fields.

    Not exposed as a POST body — workflows are created internally by the
    generation flow (``WorkflowDesignService.generate``), which supplies the
    skill, mints the design session's id, and pins the skill revision.

    ``agent_skill_commit_sha`` pins the design to the skill revision that was
    published when generation started, so a later ``pull`` of the skill cannot
    swap the design agent's code mid-conversation. Generation requires a
    published revision, so — unlike WorkflowExecution — the pin is always
    present.
    """

    name: EntityName
    agent_skill_id: str

    session_id: str
    """ADK/AG-UI id of this workflow's design session — the chat it is designed in."""

    agent_skill_commit_sha: str


class Workflow(WorkflowCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted workflow binding task templates to an agent skill.

    ``status`` and ``generation_error`` are server-managed: they are declared
    on the table class only, so they are absent from ``WorkflowCreate`` /
    ``WorkflowUpdate`` and cannot be written through the API. They are set by
    the generation background job (``services/workflow_generation.py``), by
    ``POST /workflows/{id}/publish``, ``.../discard-changes``, and
    ``.../deactivate``, and by any edit to a workflow or one of its task
    templates, whether it arrives through the API or through the design
    agent's tools (``infrastructure/design_task_tools.py``) — such an edit
    moves a ``published`` workflow to ``modified``, and a task-template write
    additionally recovers a ``failed`` one to ``draft``.

    ``generated_description`` is written only by the design generation job
    and by ``POST /workflows/{id}/generate-description``, the on-demand
    re-summarization a ``developer`` triggers from the UI (or, as a correction,
    by a ``super_admin`` through ``PATCH``); ``description`` is the free-form
    field any ``developer`` can set to override it. See
    :attr:`effective_description`.

    ``session_id`` is the workflow's design session and is indexed so the
    design agent's tools can map the session they run in back to the workflow
    whose templates they edit. ``created_by`` doubles as that chat's owner: it
    keys the ADK session, so every developer driving the conversation through
    ``/messages`` and ``/agent`` shares one history instead of forking a private
    session. Access itself is not tied to it — the chat is open to every
    ``developer`` in the tenant (see
    ``services.workflow.WorkflowService._assert_design_access``), and each
    message is attributed to its real sender through ``models.message_meta``.
    """

    __tablename__ = "workflows"

    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    status: WorkflowStatus = Field(default=WorkflowStatus.draft)
    generation_error: str | None = None

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_id_name"),
        Index("ix_workflows_tenant_id_name", "tenant_id", "name"),
        Index("ix_workflows_session_id", "session_id"),
        ForeignKeyConstraint(
            ["agent_skill_id"], ["agent_skills.id"], ondelete="RESTRICT"
        ),
    )

    @property
    def effective_description(self) -> str | None:
        """Return the description a workflow execution should use.

        ``description`` wins whenever a user has set it; otherwise falls back
        to the AI-generated ``generated_description``.
        """
        return self.description or self.generated_description


class WorkflowRead(BaseEntity):
    """Read view of a Workflow returned by the API, including its tags.

    Mirrors every column of :class:`Workflow` and adds ``tag_ids``, which lives
    in :class:`models.tag.WorkflowTag` rather than on the workflow row. The
    mirroring is not cosmetic: this class is what
    :meth:`repositories.workflow.SqlWorkflowRepository.list` passes as
    ``readable=``, and a column missing here becomes unfilterable and
    unsortable through the list API.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    description: str | None = None
    generated_description: str | None = None
    agent_skill_id: str
    session_id: str
    agent_skill_commit_sha: str
    status: WorkflowStatus = WorkflowStatus.draft
    generation_error: str | None = None
    #: Ids of the tags attached to this workflow.
    tag_ids: list[str] = []

    @classmethod
    def from_workflow(cls, workflow: Workflow, *, tag_ids: list[str]) -> "WorkflowRead":
        """Build the read view of a stored workflow with its tags attached.

        Args:
            workflow: The persisted workflow to project.
            tag_ids: Ids of the tags attached to ``workflow``.

        Returns:
            A read view carrying the workflow's columns plus its tags.
        """
        return cls(**workflow.model_dump(), tag_ids=tag_ids)


class GenerateWorkflowRequest(SQLModel):
    """Request body of ``POST /agent-skills/{skill_id}/workflows``.

    ``name`` becomes the new workflow's unique name (the UI prefills it with
    the skill name); ``prompt`` is the user's request that the background
    design run breaks into task templates.
    """

    model_config = _alias_config
    name: EntityName
    prompt: PromptText


class ExecuteWorkflowRequest(SQLModel):
    """Request body of ``POST /workflows/{workflow_id}/execute``.

    Optional in full: a body-less POST still starts an ordinary run, which is
    what every published workflow does.

    ``tool_mock_ids`` names the :class:`models.mcp_tool_mock.MCPToolMock` records
    the run should apply, stubbing those tools instead of calling them. It is
    accepted only while the workflow is still ``draft`` -- mocking a published
    workflow's tools would produce a run that looks real and did nothing.
    """

    model_config = _alias_config
    tool_mock_ids: list[str] = Field(default_factory=list)
