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

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import field_serializer
from sqlalchemy import Column, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z_or_none
from models.tenant_scoped import TenantScoped


class WorkflowExecutionStatus(StrEnum):
    """Lifecycle states a WorkflowExecution can occupy.

    The status is derived from the run's WorkflowTasks rather than set
    directly: a run finishes once it has at least one task and every task has
    reached a terminal state (``completed``/``failed``/``skipped``). See
    :meth:`services.workflow_execution.WorkflowExecutionService.evaluate_completion`,
    which both the agent's task tools and the REST task endpoints call after
    every task write.
    """

    running = "running"
    """The run is still working through its tasks (or has none yet).

    A run with no tasks at all stays ``running`` — an empty task list is
    indistinguishable from a run whose agent has not registered its tasks yet.
    """

    completed = "completed"
    """Every task reached a terminal state and none of them failed."""

    failed = "failed"
    """Every task reached a terminal state and at least one of them failed."""


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
    record. ``initiator_id`` is ``RESTRICT`` on delete, matching the audit user
    FKs on :class:`~models.base.BaseEntity` -- a user who started a run cannot
    be hard-deleted out from under it, and is soft-deleted instead so the run's
    initiator still resolves to a name.

    ``status`` and ``finished_at`` are server-managed: they are declared on the
    table class only, so they are absent from ``WorkflowExecutionCreate`` and
    cannot be written through the API. Both are stamped by
    :meth:`services.workflow_execution.WorkflowExecutionService.evaluate_completion`
    through
    :meth:`repositories.workflow_execution.SqlWorkflowExecutionRepository.mark_finished`,
    following the same pattern as :attr:`models.workflow.Workflow.status`. They
    exist to make a run's lifecycle queryable — active-run counts, per-day
    completion counts, and the ``created_at`` -> ``finished_at`` lead time all
    read them (``repositories/metrics.py``).

    ``is_draft`` is server-managed the same way, but set once at creation rather
    than stamped later: :meth:`services.workflow.WorkflowService.execute` passes
    ``True`` for a run that executes a design nobody has approved — the workflow
    is still :attr:`models.workflow.WorkflowStatus.draft`, or it is ``modified``
    and a ``developer`` asked to run its unpublished edits
    (:attr:`models.workflow.WorkflowDesignSource.live`). Either way it is a
    ``developer``/``super_admin`` pre-publish test run, and the flag is never
    updated afterwards, so publishing the workflow does not reclassify runs that
    already happened. Draft runs are omitted from every query in
    ``repositories/metrics.py`` so throwaway test data does not skew the
    operations metrics.

    ``tool_mocks`` and ``tool_mock_calls`` drive the run's mocked tools (see
    :mod:`models.mcp_tool_mock`). ``tool_mocks`` is a **snapshot** of the
    :class:`~models.mcp_tool_mock.MCPToolMock` rows selected when the run
    started, not a list of their ids: editing or deleting a mock afterwards must
    not change how a run behaves, and above all must never silently turn a
    stubbed call back into a real one with live side effects. Only a draft run
    may carry mocks. ``tool_mock_calls`` counts how many times each mocked tool
    has been called so far, keyed ``"<server_id or 'builtin'>:<tool_name>"``,
    which is what selects the per-ordinal response.
    """

    __tablename__ = "workflow_executions"
    workflow_id: str | None = None
    is_draft: bool = Field(default=False)
    tool_mocks: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
    tool_mock_calls: dict[str, int] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )
    status: WorkflowExecutionStatus = Field(default=WorkflowExecutionStatus.running)
    finished_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    __table_args__ = (
        Index("ix_workflow_executions_session_id", "session_id"),
        Index("ix_workflow_executions_tenant_id_status", "tenant_id", "status"),
        Index("ix_workflow_executions_tenant_id_created_at", "tenant_id", "created_at"),
        ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
        ForeignKeyConstraint(["initiator_id"], ["users.id"], ondelete="RESTRICT"),
    )

    @field_serializer("finished_at", when_used="json")
    def _serialize_finished_at(self, dt: datetime | None) -> str | None:
        """Serialize ``finished_at`` as ISO-8601 with a ``Z`` suffix, or ``None``.

        Args:
            dt: The completion timestamp, or ``None`` while the run is active.

        Returns:
            The ISO-8601 string with a ``Z`` suffix, or ``None``.
        """
        return iso_z_or_none(dt)
