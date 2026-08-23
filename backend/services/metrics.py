"""Use case service folding raw metric rows into the shapes the API returns.

Two consumers sit on top of this service and they want different things:

* ``GET /metrics`` wants a handful of single numbers, cheap enough to recompute
  on every Prometheus scrape — :meth:`MetricsService.snapshot`.
* The aggregate sub-resources on the workflow-execution and approval routers
  want breakdowns and ranked lists, which Prometheus labels would model badly —
  the remaining methods.

Both read through :class:`repositories.metrics.MetricsRepository`, which is
already scoped to the caller's tenant, so nothing here needs a tenant check of
its own.

Two conventions run through the whole module. Durations are whole-second
``float``s, never interval objects, so no client has to parse a format. And
"today" and the daily buckets are resolved in the timezone named by
``METRICS_TIMEZONE`` rather than UTC, because a completion count is read against
somebody's working day.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from models.approval import ApprovalStatus
from models.metrics import (
    ApprovalBacklogEntry,
    FailedExecutionEntry,
    FailedTaskEntry,
    LeadTimeBucket,
    WorkflowVolumeEntry,
)
from models.workflow_execution import WorkflowExecutionStatus
from repositories.metrics import ApprovalRow, ExecutionRow, MetricsRepository
from repositories.outbound_email import OutboundEmailRepository

#: Label used in place of a missing failure classification, so a Prometheus
#: series never carries an empty label value.
UNCLASSIFIED = "unclassified"

#: Label used in place of a deleted workflow's name when grouping runs whose
#: workflow design is gone.
UNKNOWN_WORKFLOW = "unknown"

#: Rolling window, in hours, behind the "recent failures" and "recent volume"
#: gauges. Matches the 24-hour framing the operations view is built around.
RECENT_WINDOW_HOURS = 24


@dataclass(frozen=True)
class MetricsWindow:
    """A half-open ``[since, until)`` time window for the aggregate endpoints."""

    since: datetime
    until: datetime


@dataclass(frozen=True)
class MetricsSnapshot:
    """The single-value KPIs exported through the Prometheus endpoint.

    Deliberately plain data: :mod:`routers.metrics` turns this into exposition
    text and nothing else consumes it, so the two can evolve together without
    the aggregation logic knowing anything about Prometheus.
    """

    approvals_pending: int
    approvals_pending_over_threshold: int
    approval_pending_age_seconds_max: float
    executions_active: int
    executions_finished_today: dict[str, int] = field(default_factory=dict)
    approvals_decided_today: dict[str, int] = field(default_factory=dict)
    executions_failed_recently: int = 0
    tasks_failed_recently: dict[str, int] = field(default_factory=dict)
    executions_started_recently: dict[str, int] = field(default_factory=dict)
    lead_time_seconds_avg_recently: dict[str, float] = field(default_factory=dict)
    #: Queued notification emails per ``OutboundEmailStatus`` value. Always
    #: carries every status, zeros included, so a drained queue keeps exporting
    #: a series instead of making one vanish from the exposition.
    email_queue_depth: dict[str, int] = field(default_factory=dict)
    #: Age of the tenant's longest-waiting undelivered email, or zero when
    #: nothing is waiting. Rises when the relay is unreachable.
    email_queue_oldest_pending_age_seconds: float = 0.0


def _mean(values: list[float]) -> float | None:
    """Return the arithmetic mean, or ``None`` for an empty list."""
    return sum(values) / len(values) if values else None


def _lead_time_seconds(execution: ExecutionRow) -> float | None:
    """Return a run's ``created_at`` -> ``finished_at`` duration in seconds, if finished."""
    if execution.finished_at is None:
        return None
    return (execution.finished_at - execution.created_at).total_seconds()


class MetricsService:
    """Application service producing the workflow operations metrics."""

    def __init__(
        self,
        repo: MetricsRepository,
        emails: OutboundEmailRepository,
        *,
        timezone: str,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing the tenant-scoped aggregate reads.
            emails: Repository reporting the tenant's outgoing-email backlog.
                Notification email is delivered asynchronously, so how far
                behind that queue is running is an operational number like any
                other here.
            timezone: IANA timezone name deciding where a calendar day starts.
                Already validated by ``Settings``, which falls back to UTC on an
                unrecognized name.
        """
        self._repo = repo
        self._emails = emails
        self._tz = ZoneInfo(timezone)

    def _now(self) -> datetime:
        """Return the current UTC time; isolated so tests can override it."""
        return datetime.now(UTC)

    def _day_start(self, moment: datetime) -> datetime:
        """Return midnight starting the local calendar day containing ``moment``.

        Args:
            moment: Any timezone-aware instant.

        Returns:
            The corresponding local midnight, as a UTC-comparable aware
            datetime.
        """
        local = moment.astimezone(self._tz)
        return local.replace(hour=0, minute=0, second=0, microsecond=0)

    def _local_date(self, moment: datetime) -> date:
        """Return the local calendar date ``moment`` falls on."""
        return moment.astimezone(self._tz).date()

    async def volume_by_workflow(
        self, window: MetricsWindow, *, limit: int
    ) -> list[WorkflowVolumeEntry]:
        """Return per-workflow run counts and average lead time over a window.

        Runs are attributed to the workflow they were started from; runs whose
        workflow has since been deleted collapse into a single ``None`` group
        rather than disappearing, so historical volume stays honest.

        Args:
            window: The time window, applied to each run's start time.
            limit: Maximum number of workflows to return, busiest first.

        Returns:
            The per-workflow entries, ordered by ``total`` descending.
        """
        rows = await self._repo.executions_started_between(window.since, window.until)
        grouped: dict[str | None, list[ExecutionRow]] = defaultdict(list)
        for row in rows:
            grouped[row.workflow_id].append(row)

        entries = [
            WorkflowVolumeEntry(
                workflow_id=workflow_id,
                workflow_name=group[0].workflow_name,
                total=len(group),
                running=sum(
                    1 for r in group if r.status == WorkflowExecutionStatus.running
                ),
                completed=sum(
                    1 for r in group if r.status == WorkflowExecutionStatus.completed
                ),
                failed=sum(
                    1 for r in group if r.status == WorkflowExecutionStatus.failed
                ),
                avg_lead_time_seconds=_mean(
                    [
                        seconds
                        for r in group
                        if (seconds := _lead_time_seconds(r)) is not None
                    ]
                ),
            )
            for workflow_id, group in grouped.items()
        ]
        entries.sort(key=lambda e: (-e.total, e.workflow_name))
        return entries[:limit]

    async def lead_time_trend(self, window: MetricsWindow) -> list[LeadTimeBucket]:
        """Return the daily average lead time of runs finishing within a window.

        Every local calendar day the window touches gets a bucket, including
        days on which nothing finished, so a client can draw a continuous line
        without reconstructing the gaps.

        Args:
            window: The time window, applied to each run's completion time.

        Returns:
            One bucket per day, oldest first.
        """
        rows = await self._repo.executions_finished_between(window.since, window.until)
        by_day: dict[date, list[float]] = defaultdict(list)
        for row in rows:
            if row.finished_at is None:
                continue
            seconds = _lead_time_seconds(row)
            if seconds is not None:
                by_day[self._local_date(row.finished_at)].append(seconds)

        buckets: list[LeadTimeBucket] = []
        day = self._local_date(window.since)
        last_day = self._local_date(window.until - timedelta(microseconds=1))
        while day <= last_day:
            durations = by_day.get(day, [])
            buckets.append(
                LeadTimeBucket(
                    bucket_start=datetime.combine(
                        day, datetime.min.time(), tzinfo=self._tz
                    ),
                    count=len(durations),
                    avg_lead_time_seconds=_mean(durations),
                )
            )
            day += timedelta(days=1)
        return buckets

    async def failed_executions(
        self, window: MetricsWindow, *, limit: int
    ) -> list[FailedExecutionEntry]:
        """Return the runs with failed tasks in a window, newest failure first.

        This is the triage list. It is driven by the failed *tasks* rather than
        by the runs' own status, so a run that is still in flight but already
        has a failed task shows up immediately instead of waiting for the run
        to finish.

        Args:
            window: The time window, applied to each task's failure time.
            limit: Maximum number of runs to return.

        Returns:
            The affected runs, each carrying its failed tasks.
        """
        rows = await self._repo.failed_tasks_between(window.since, window.until)
        entries: dict[str, FailedExecutionEntry] = {}
        for row in rows:
            entry = entries.get(row.execution_id)
            if entry is None:
                # Stop admitting new runs at the limit, but keep collecting the
                # remaining failed tasks of the runs already admitted -- an
                # entry must carry every one of its failures to be triageable.
                if len(entries) >= limit:
                    continue
                entry = FailedExecutionEntry(
                    execution_id=row.execution_id,
                    name=row.execution_name,
                    workflow_id=row.workflow_id,
                    workflow_name=row.workflow_name,
                    status=row.execution_status,
                    finished_at=row.execution_finished_at,
                    failed_tasks=[],
                )
                entries[row.execution_id] = entry
            entry.failed_tasks.append(
                FailedTaskEntry(
                    task_id=row.task_id,
                    title=row.title,
                    error_kind=row.error_kind,
                    error_message=row.error_message,
                    failed_at=row.failed_at,
                )
            )
        return list(entries.values())

    @staticmethod
    def _backlog_kind(
        row: ApprovalRow, *, key: str
    ) -> Literal["user", "group", "workflow"] | None:
        """Return what an entry's ``group_id`` refers to, or ``None`` when it has none.

        Args:
            row: Any approval from the group, since every row in one group
                shares the same key.
            key: The grouping axis, ``"approver"`` or ``"workflow"``.

        Returns:
            ``"workflow"`` on the by-workflow axis, ``"user"`` or ``"group"`` on
            the by-approver axis, or ``None`` when the key itself is ``None``.
        """
        if key != "approver":
            return "workflow" if row.workflow_id is not None else None
        if row.approver is not None:
            return "user"
        if row.approver_group_id is not None:
            return "group"
        return None

    def _backlog(
        self,
        rows: list[ApprovalRow],
        *,
        key: str,
        threshold_hours: float,
        limit: int,
    ) -> list[ApprovalBacklogEntry]:
        """Fold pending approvals into backlog entries on one grouping axis.

        Args:
            rows: The pending approvals to group.
            key: ``"approver"`` to group by the approval's destination (its
                designated user, or the group it is addressed to), or
                ``"workflow"`` to group by the workflow the run belongs to.
            threshold_hours: Waiting time beyond which an approval counts as
                stalled.
            limit: Maximum number of groups to return.

        Returns:
            The backlog entries, longest single wait first.
        """
        now = self._now()
        threshold = timedelta(hours=threshold_hours).total_seconds()
        grouped: dict[str | None, list[ApprovalRow]] = defaultdict(list)
        for row in rows:
            if key == "approver":
                # ck_approvals_single_destination keeps at most one of the two
                # set; prefer the user so a hypothetical both-set row is still
                # counted once, under the narrower key.
                grouped[row.approver or row.approver_group_id].append(row)
            else:
                grouped[row.workflow_id].append(row)

        entries: list[ApprovalBacklogEntry] = []
        for group_id, group in grouped.items():
            waits = [(now - r.created_at).total_seconds() for r in group]
            entries.append(
                ApprovalBacklogEntry(
                    group_id=group_id,
                    group_kind=self._backlog_kind(group[0], key=key),
                    group_label=(
                        group[0].workflow_name
                        if key != "approver"
                        else (
                            None
                            if group[0].approver is not None
                            else group[0].approver_group_name
                        )
                    ),
                    pending=len(group),
                    over_threshold=sum(1 for w in waits if w > threshold),
                    avg_wait_seconds=sum(waits) / len(waits),
                    max_wait_seconds=max(waits),
                )
            )
        entries.sort(key=lambda e: -e.max_wait_seconds)
        return entries[:limit]

    async def approval_backlog_by_approver(
        self, *, threshold_hours: float, limit: int
    ) -> list[ApprovalBacklogEntry]:
        """Return the pending-approval backlog grouped by approval destination.

        One entry per designated user or approver group. ``group_kind`` on each
        entry says which of the two its ``group_id`` is, since the ids are
        indistinguishable as bare UUIDs and only user ids resolve through
        ``POST /users/resolve-names``.

        Args:
            threshold_hours: Waiting time beyond which an approval counts as
                stalled.
            limit: Maximum number of destinations to return.

        Returns:
            The backlog entries, longest single wait first.
        """
        rows = await self._repo.pending_approvals()
        return self._backlog(
            rows, key="approver", threshold_hours=threshold_hours, limit=limit
        )

    async def approval_backlog_by_workflow(
        self, *, threshold_hours: float, limit: int
    ) -> list[ApprovalBacklogEntry]:
        """Return the pending-approval backlog grouped by workflow.

        Args:
            threshold_hours: Waiting time beyond which an approval counts as
                stalled.
            limit: Maximum number of workflows to return.

        Returns:
            The backlog entries, longest single wait first.
        """
        rows = await self._repo.pending_approvals()
        return self._backlog(
            rows, key="workflow", threshold_hours=threshold_hours, limit=limit
        )

    async def snapshot(self, *, threshold_hours: float) -> MetricsSnapshot:
        """Return the single-value KPIs for one Prometheus scrape.

        Args:
            threshold_hours: Waiting time beyond which a pending approval counts
                as stalled.

        Returns:
            The snapshot, with every count already reduced to a plain number or
            a small label-to-number mapping.
        """
        now = self._now()
        day_start = self._day_start(now)
        recent_start = now - timedelta(hours=RECENT_WINDOW_HOURS)
        threshold = timedelta(hours=threshold_hours).total_seconds()

        pending = await self._repo.pending_approvals()
        waits = [(now - r.created_at).total_seconds() for r in pending]

        by_status = await self._repo.count_executions_by_status()

        finished_today = await self._repo.executions_finished_between(day_start, now)
        decided_today = await self._repo.approvals_decided_between(day_start, now)
        finished_recently = await self._repo.executions_finished_between(
            recent_start, now
        )
        started_recently = await self._repo.executions_started_between(
            recent_start, now
        )
        failed_tasks = await self._repo.failed_tasks_between(recent_start, now)

        email_depth = await self._emails.counts_by_status()
        email_oldest = await self._emails.oldest_pending_age_seconds(now=now)

        finished_today_counts: dict[str, int] = defaultdict(int)
        for row in finished_today:
            finished_today_counts[row.status.value] += 1

        decided_counts: dict[str, int] = defaultdict(int)
        for status in (
            ApprovalStatus.approved,
            ApprovalStatus.rejected,
            ApprovalStatus.returned,
        ):
            decided_counts[status.value] = 0
        for approval in decided_today:
            decided_counts[approval.status.value] += 1

        failed_task_counts: dict[str, int] = defaultdict(int)
        for task in failed_tasks:
            failed_task_counts[
                task.error_kind.value if task.error_kind else UNCLASSIFIED
            ] += 1

        started_counts: dict[str, int] = defaultdict(int)
        for row in started_recently:
            started_counts[row.workflow_name or UNKNOWN_WORKFLOW] += 1

        lead_times: dict[str, list[float]] = defaultdict(list)
        for row in finished_recently:
            seconds = _lead_time_seconds(row)
            if seconds is not None:
                lead_times[row.workflow_name or UNKNOWN_WORKFLOW].append(seconds)

        return MetricsSnapshot(
            approvals_pending=len(pending),
            approvals_pending_over_threshold=sum(1 for w in waits if w > threshold),
            approval_pending_age_seconds_max=max(waits, default=0.0),
            executions_active=by_status.get(WorkflowExecutionStatus.running, 0),
            executions_finished_today=dict(finished_today_counts),
            approvals_decided_today=dict(decided_counts),
            executions_failed_recently=sum(
                1
                for row in finished_recently
                if row.status == WorkflowExecutionStatus.failed
            ),
            tasks_failed_recently=dict(failed_task_counts),
            executions_started_recently=dict(started_counts),
            lead_time_seconds_avg_recently={
                name: sum(values) / len(values) for name, values in lead_times.items()
            },
            email_queue_depth={
                status.value: count for status, count in email_depth.items()
            },
            email_queue_oldest_pending_age_seconds=email_oldest or 0.0,
        )
