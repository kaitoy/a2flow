"""Tenant-scoped read queries backing the workflow operations metrics.

Every method here selects the minimum set of columns for one question, over a
bounded time window, and hands back plain frozen rows. All folding — grouping,
averaging, day bucketing — happens in :mod:`services.metrics`, deliberately:

* **No dialect-specific date functions.** ``date_trunc`` (PostgreSQL) and
  ``strftime`` (SQLite) have no common spelling, and calendar-day boundaries
  depend on the configured metrics timezone anyway. Bucketing in Python keeps
  one implementation that behaves identically on whichever backend ``DB_URL``
  selects.
* **One place to change if this ever needs to scale.** The window is bounded and
  the row counts are small at present, so pulling rows and folding them is both
  simpler and easier to test than assembling grouped SQL. If the volume ever
  outgrows that, this module is the only thing that has to be rewritten — the
  service and router contracts do not change.

Like every other tenant-scoped repository, each query filters on the tenant
resolved by ``CurrentTenantIdDep``; there is no cross-tenant read here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalStatus
from models.workflow import Workflow
from models.workflow_execution import WorkflowExecution, WorkflowExecutionStatus
from models.workflow_task import TaskErrorKind, WorkflowTask, WorkflowTaskStatus


def _utc(value: datetime) -> datetime:
    """Normalize a datetime read from the database to a timezone-aware UTC value.

    ``TZDateTime`` maps to ``timestamptz`` on PostgreSQL but is a storage no-op
    on SQLite, which hands values back naive. Everything downstream subtracts
    these from :func:`datetime.now(UTC) <datetime.datetime.now>`, which raises
    on a naive operand, so the rows are normalized here at the boundary rather
    than defensively at every arithmetic site. Naive values are read as UTC —
    the same assumption :func:`models.base.iso_z` makes when serializing them.

    Args:
        value: A timestamp as returned by the driver.

    Returns:
        The timezone-aware UTC equivalent.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _utc_or_none(value: datetime | None) -> datetime | None:
    """Apply :func:`_utc` to an optional timestamp, passing ``None`` through."""
    return None if value is None else _utc(value)


@dataclass(frozen=True)
class ExecutionRow:
    """One workflow run, reduced to the columns the metrics need."""

    execution_id: str
    workflow_id: str | None
    workflow_name: str
    execution_name: str
    status: WorkflowExecutionStatus
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class ApprovalRow:
    """One approval request, reduced to the columns the metrics need."""

    approval_id: str
    approver: str | None
    workflow_id: str | None
    workflow_name: str
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True)
class FailedTaskRow:
    """One failed task, joined to the run and workflow it belongs to."""

    task_id: str
    title: str
    error_kind: TaskErrorKind | None
    error_message: str | None
    failed_at: datetime
    execution_id: str
    execution_name: str
    execution_status: WorkflowExecutionStatus
    execution_finished_at: datetime | None
    workflow_id: str | None
    workflow_name: str


class MetricsRepository(Protocol):
    """Interface for the aggregate read queries behind the operations metrics."""

    async def executions_started_between(
        self, since: datetime, until: datetime
    ) -> list[ExecutionRow]: ...

    async def executions_finished_between(
        self, since: datetime, until: datetime
    ) -> list[ExecutionRow]: ...

    async def count_executions_by_status(
        self,
    ) -> dict[WorkflowExecutionStatus, int]: ...

    async def pending_approvals(self) -> list[ApprovalRow]: ...

    async def approvals_decided_between(
        self, since: datetime, until: datetime
    ) -> list[ApprovalRow]: ...

    async def failed_tasks_between(
        self, since: datetime, until: datetime
    ) -> list[FailedTaskRow]: ...


class SqlMetricsRepository:
    """SQLModel-backed implementation of :class:`MetricsRepository`."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the async session and the tenant every query below is scoped to.

        Args:
            session: The SQLModel async session to query through.
            tenant_id: Identifier of the tenant these metrics describe.
        """
        self._db = session
        self._tenant_id = tenant_id

    def _execution_columns(self) -> Sequence[object]:
        """Return the execution/workflow column list shared by the execution queries."""
        return (
            WorkflowExecution.id,
            WorkflowExecution.workflow_id,
            Workflow.name,
            WorkflowExecution.name,
            WorkflowExecution.status,
            WorkflowExecution.created_at,
            WorkflowExecution.finished_at,
        )

    async def _executions_where(self, *conditions: object) -> list[ExecutionRow]:
        """Run the shared execution select under extra conditions.

        The join to ``workflows`` is an outer join because a run outlives its
        workflow design: ``workflow_id`` is ``SET NULL`` on delete, so the
        workflow row may be gone while the run still counts toward history. In
        that case the run's own ``name`` snapshot stands in for the workflow
        name.

        Args:
            *conditions: Extra ``WHERE`` clauses, applied on top of the tenant
                scope.

        Returns:
            The matching runs, newest first.
        """
        stmt = (
            select(*self._execution_columns())  # type: ignore[call-overload]
            .join(
                Workflow,
                col(WorkflowExecution.workflow_id) == Workflow.id,
                isouter=True,
            )
            .where(WorkflowExecution.tenant_id == self._tenant_id, *conditions)
            .order_by(col(WorkflowExecution.created_at).desc())
        )
        result = await self._db.exec(stmt)
        return [
            ExecutionRow(
                execution_id=row[0],
                workflow_id=row[1],
                workflow_name=row[2] or row[3],
                execution_name=row[3],
                status=row[4],
                created_at=_utc(row[5]),
                finished_at=_utc_or_none(row[6]),
            )
            for row in result.all()
        ]

    async def executions_started_between(
        self, since: datetime, until: datetime
    ) -> list[ExecutionRow]:
        """Return the runs started within ``[since, until)``.

        Args:
            since: Inclusive lower bound on ``created_at``.
            until: Exclusive upper bound on ``created_at``.

        Returns:
            The matching runs, newest first.
        """
        return await self._executions_where(
            col(WorkflowExecution.created_at) >= since,
            col(WorkflowExecution.created_at) < until,
        )

    async def executions_finished_between(
        self, since: datetime, until: datetime
    ) -> list[ExecutionRow]:
        """Return the runs that finished within ``[since, until)``.

        Args:
            since: Inclusive lower bound on ``finished_at``.
            until: Exclusive upper bound on ``finished_at``.

        Returns:
            The matching runs, newest first.
        """
        return await self._executions_where(
            col(WorkflowExecution.finished_at).is_not(None),
            col(WorkflowExecution.finished_at) >= since,
            col(WorkflowExecution.finished_at) < until,
        )

    async def count_executions_by_status(self) -> dict[WorkflowExecutionStatus, int]:
        """Return the current run count per lifecycle status.

        Unlike the windowed queries this is a point-in-time snapshot of the
        whole tenant, because "how many runs are active right now" has no
        meaningful time window.

        Returns:
            A count per status; statuses with no runs are absent.
        """
        stmt = (
            select(WorkflowExecution.status, func.count())
            .where(WorkflowExecution.tenant_id == self._tenant_id)
            .group_by(col(WorkflowExecution.status))
        )
        result = await self._db.exec(stmt)
        return {WorkflowExecutionStatus(row[0]): row[1] for row in result.all()}

    async def _approvals_where(self, *conditions: object) -> list[ApprovalRow]:
        """Run the shared approval select under extra conditions.

        Approvals reach their workflow through the run they belong to, so this
        joins ``workflow_executions`` (inner — an approval always has a run)
        and then ``workflows`` (outer, for the same reason as
        :meth:`_executions_where`).

        Args:
            *conditions: Extra ``WHERE`` clauses, applied on top of the tenant
                scope.

        Returns:
            The matching approvals, oldest first, so the longest-waiting
            request leads.
        """
        stmt = (
            select(  # type: ignore[call-overload]
                Approval.id,
                Approval.approver,
                WorkflowExecution.workflow_id,
                Workflow.name,
                WorkflowExecution.name,
                Approval.status,
                Approval.created_at,
                Approval.decided_at,
            )
            .join(
                WorkflowExecution,
                col(Approval.workflow_execution_id) == WorkflowExecution.id,
            )
            .join(
                Workflow,
                col(WorkflowExecution.workflow_id) == Workflow.id,
                isouter=True,
            )
            .where(Approval.tenant_id == self._tenant_id, *conditions)
            .order_by(col(Approval.created_at).asc())
        )
        result = await self._db.exec(stmt)
        return [
            ApprovalRow(
                approval_id=row[0],
                approver=row[1],
                workflow_id=row[2],
                workflow_name=row[3] or row[4],
                status=row[5],
                created_at=_utc(row[6]),
                decided_at=_utc_or_none(row[7]),
            )
            for row in result.all()
        ]

    async def pending_approvals(self) -> list[ApprovalRow]:
        """Return every approval still awaiting a decision, oldest first.

        Not windowed: an approval that has been pending for a month is exactly
        the one the backlog view exists to surface.

        Returns:
            The pending approvals, oldest first.
        """
        return await self._approvals_where(Approval.status == ApprovalStatus.pending)

    async def approvals_decided_between(
        self, since: datetime, until: datetime
    ) -> list[ApprovalRow]:
        """Return the approvals decided within ``[since, until)``.

        Args:
            since: Inclusive lower bound on ``decided_at``.
            until: Exclusive upper bound on ``decided_at``.

        Returns:
            The matching approvals, oldest first.
        """
        return await self._approvals_where(
            col(Approval.decided_at).is_not(None),
            col(Approval.decided_at) >= since,
            col(Approval.decided_at) < until,
        )

    async def failed_tasks_between(
        self, since: datetime, until: datetime
    ) -> list[FailedTaskRow]:
        """Return the tasks that failed within ``[since, until)``, newest first.

        The window is applied to the task's ``updated_at``. WorkflowTask has no
        dedicated failure timestamp: a failure and its cause are written in the
        same update, so the last write is the failure time in practice. A task
        edited after it failed is dated by that later edit — an acceptable
        approximation, and the reason this is not presented as an exact
        failure time (see :class:`models.metrics.FailedTaskEntry`).

        Args:
            since: Inclusive lower bound on ``updated_at``.
            until: Exclusive upper bound on ``updated_at``.

        Returns:
            The matching failed tasks, most recently written first.
        """
        stmt = (
            select(  # type: ignore[call-overload]
                WorkflowTask.id,
                WorkflowTask.title,
                WorkflowTask.error_kind,
                WorkflowTask.error_message,
                WorkflowTask.updated_at,
                WorkflowExecution.id,
                WorkflowExecution.name,
                WorkflowExecution.status,
                WorkflowExecution.finished_at,
                WorkflowExecution.workflow_id,
                Workflow.name,
            )
            .join(
                WorkflowExecution,
                col(WorkflowTask.workflow_execution_id) == WorkflowExecution.id,
            )
            .join(
                Workflow,
                col(WorkflowExecution.workflow_id) == Workflow.id,
                isouter=True,
            )
            .where(
                WorkflowTask.tenant_id == self._tenant_id,
                WorkflowTask.status == WorkflowTaskStatus.failed,
                col(WorkflowTask.updated_at) >= since,
                col(WorkflowTask.updated_at) < until,
            )
            .order_by(col(WorkflowTask.updated_at).desc())
        )
        result = await self._db.exec(stmt)
        return [
            FailedTaskRow(
                task_id=row[0],
                title=row[1],
                error_kind=row[2],
                error_message=row[3],
                failed_at=_utc(row[4]),
                execution_id=row[5],
                execution_name=row[6],
                execution_status=row[7],
                execution_finished_at=_utc_or_none(row[8]),
                workflow_id=row[9],
                workflow_name=row[10] or row[6],
            )
            for row in result.all()
        ]
