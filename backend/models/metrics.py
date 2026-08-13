"""Read models for the workflow operations metrics.

These are response-only shapes: nothing here is persisted. Each one is an
aggregate folded from the workflow execution, task, and approval tables by
:mod:`services.metrics`, and each answers one question an operations dashboard
asks — which workflows run most, how long they take end to end, whose approval
queue is backing up, and which runs need a human to look at them.

The numeric single-value KPIs (active runs, today's completions, approval
counts) are not here: they are served in Prometheus exposition format by
``GET /metrics``. This module covers only the breakdowns and lists, which
Prometheus labels would model badly — an approver id or a failure message is
per-record data, not a bounded label set.

Every duration is expressed in whole seconds so a client never has to parse an
interval format, and ``None`` where no member of the group had one to measure.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

from models.base import iso_z, iso_z_or_none
from models.workflow_execution import WorkflowExecutionStatus
from models.workflow_task import TaskErrorKind

_alias_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkflowVolumeEntry(BaseModel):
    """Run volume and average lead time for one workflow over a time window.

    Backs the per-workflow execution-volume bar chart and doubles as the
    failure-rate breakdown, since the status counts sit alongside the total.
    """

    model_config = _alias_config

    workflow_id: str | None
    """The workflow these runs belong to, or ``None`` once it has been deleted.

    Runs outlive their workflow design (``workflow_id`` is ``SET NULL`` on
    delete), and they still count toward historical volume, so they are grouped
    under a single ``None`` bucket rather than dropped.
    """

    workflow_name: str
    """The workflow's current name, or the run's own name snapshot when the workflow is gone."""

    total: int
    """Runs started within the window."""

    running: int
    """Of ``total``, those still in flight."""

    completed: int
    """Of ``total``, those that finished with no failed task."""

    failed: int
    """Of ``total``, those that finished with at least one failed task."""

    avg_lead_time_seconds: float | None
    """Mean ``created_at`` -> ``finished_at`` duration over the finished runs, or ``None``."""


class LeadTimeBucket(BaseModel):
    """One day's worth of finished runs on the lead-time trend line.

    Buckets are keyed by the calendar day the run *finished*, in the timezone
    configured by ``METRICS_TIMEZONE``. Days with no finished run are still
    present, with ``count`` zero and ``avg_lead_time_seconds`` ``None``, so a
    client can plot the series without filling gaps itself.
    """

    model_config = _alias_config

    bucket_start: datetime
    """Midnight at the start of the day, in the configured metrics timezone."""

    count: int
    """Runs that finished during the day."""

    avg_lead_time_seconds: float | None
    """Mean ``created_at`` -> ``finished_at`` duration over those runs, or ``None``."""

    @field_serializer("bucket_start")
    def _serialize_bucket_start(self, value: datetime) -> str:
        """Serialize the bucket boundary as ISO-8601 with a ``Z`` suffix."""
        return iso_z(value)


class FailedTaskEntry(BaseModel):
    """One failed task inside a failed run, with the cause the agent recorded."""

    model_config = _alias_config

    task_id: str
    title: str

    error_kind: TaskErrorKind | None
    """The recorded failure cause, or ``None`` if the agent did not classify it."""

    error_message: str | None
    """Free-text detail accompanying ``error_kind``."""

    failed_at: datetime
    """When the task was last written, used as its failure time.

    The task table records no dedicated failure timestamp; a failure and its
    cause are written together, so the last write is the failure in practice.
    A task edited after it failed reports the later edit instead.
    """

    @field_serializer("failed_at")
    def _serialize_failed_at(self, value: datetime) -> str:
        """Serialize the failure time as ISO-8601 with a ``Z`` suffix."""
        return iso_z(value)


class FailedExecutionEntry(BaseModel):
    """A run that ended in failure, together with the tasks that failed in it.

    This is the "needs attention" list: one entry per run a human has to triage,
    already carrying the causes so the client does not have to fetch each run's
    tasks separately.
    """

    model_config = _alias_config

    execution_id: str
    name: str
    workflow_id: str | None
    workflow_name: str
    status: WorkflowExecutionStatus

    finished_at: datetime | None
    """When the run finished, or ``None`` for a run still carrying failed tasks."""

    failed_tasks: list[FailedTaskEntry]
    """The run's failed tasks, most recently failed first."""

    @field_serializer("finished_at")
    def _serialize_finished_at(self, value: datetime | None) -> str | None:
        """Serialize the completion time as ISO-8601 with a ``Z`` suffix, or ``None``."""
        return iso_z_or_none(value)


class ApprovalBacklogEntry(BaseModel):
    """Pending-approval backlog for one approver or one workflow.

    The same shape serves both axes of the approval-backlog view — grouped by
    approver, and grouped by the workflow the approvals belong to — because the
    measures are identical and only the grouping key differs. Entries come back
    sorted by ``max_wait_seconds`` descending, so taking the first five gives
    the worst five.
    """

    model_config = _alias_config

    group_id: str | None
    """The approver's user id or the workflow's id, depending on the endpoint.

    ``None`` covers approvals with no designated approver, and runs whose
    workflow has been deleted.
    """

    group_label: str | None
    """The workflow's name on the by-workflow axis; ``None`` on the by-approver axis.

    Approver names are deliberately not resolved here — visibility of another
    user's name is ``UserService``'s decision, and clients already resolve ids
    to names in bulk through ``POST /users/resolve-names``.
    """

    pending: int
    """Approvals still awaiting a decision."""

    over_threshold: int
    """Of ``pending``, those waiting longer than the requested threshold."""

    avg_wait_seconds: float
    """Mean time the pending approvals have been waiting so far."""

    max_wait_seconds: float
    """Longest a single pending approval has been waiting; the sort key."""
