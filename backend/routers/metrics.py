"""Prometheus exposition of the workflow operations KPIs.

``GET /api/v1/metrics`` renders the single-value KPIs — pending approvals,
active runs, today's completions, recent failures, per-workflow volume and lead
time — in Prometheus text exposition format, so Grafana and anything else that
scrapes Prometheus can chart them without a bespoke integration.

**What is deliberately *not* here.** Anything whose natural key is a user id, an
execution id, or a free-text error message stays out: those are unbounded label
sets, and a time-series database is the wrong shape for them. The ranked and
listed views live on the aggregate sub-resources of the workflow-execution and
approval routers instead (``models/metrics.py``).

**Scope.** Like every other resource route, this one runs under the session
guard in ``routers/__init__.py`` and reads through the tenant resolved by
``CurrentTenantIdDep``. A scrape therefore covers exactly one tenant, and every
sample carries a ``tenant`` label naming it. To watch several tenants, give
Prometheus one scrape job per tenant.

**Scraping it.** The endpoint is protected by the ordinary session cookie, so
the scrape config has to carry one; ``GET`` is a safe method, so no CSRF token
is needed::

    - job_name: a2flow
      metrics_path: /api/v1/metrics
      http_headers:
        Cookie: { values: ["a2flow_session=<token>"] }

The session's idle timeout slides on every request, so a running scrape keeps
its own session alive indefinitely. It does not survive a backend restart or an
explicit logout, which is when the token has to be refreshed.
"""

from collections.abc import Iterable, Iterator

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily

from dependencies import BacklogThresholdDep, CurrentTenantIdDep, MetricsServiceDep
from services.metrics import RECENT_WINDOW_HOURS, MetricsSnapshot

router = APIRouter()

#: Prefix shared by every series, keeping the application's metrics in one
#: namespace on a Prometheus server that also scrapes other things.
_PREFIX = "a2flow"


class _SnapshotCollector:
    """Collector yielding metric families that were already built and filled.

    ``prometheus_client`` renders through a registry of *collectors*, and its
    built-in ones own their own state. Here the values are read from the
    database per scrape, so there is no state to own — this adapter just hands
    the pre-built families to :func:`generate_latest`.
    """

    def __init__(self, families: Iterable[GaugeMetricFamily]) -> None:
        """Store the families this collector will yield.

        Args:
            families: The gauge families to expose, already populated.
        """
        self._families = list(families)

    def collect(self) -> Iterator[GaugeMetricFamily]:
        """Yield each stored metric family, as the registry's contract requires."""
        yield from self._families


def _render(snapshot: MetricsSnapshot, tenant_id: str, threshold_hours: float) -> str:
    """Render a snapshot as Prometheus text exposition.

    Builds a fresh :class:`CollectorRegistry` per call rather than using the
    process-global default one. These values come from the database, not from
    process state, so there is nothing to accumulate between scrapes — and a
    per-call registry keeps two concurrent scrapes from writing over each
    other's gauges.

    Args:
        snapshot: The KPI values to expose.
        tenant_id: Identifier of the tenant every sample is labelled with.
        threshold_hours: The stalled-approval threshold, echoed as a label so a
            dashboard shows which cutoff produced the number.

    Returns:
        The exposition text.
    """
    recent = f"{RECENT_WINDOW_HOURS}h"
    families: list[GaugeMetricFamily] = []

    def gauge(
        name: str, documentation: str, extra_labels: tuple[str, ...] = ()
    ) -> GaugeMetricFamily:
        """Create a gauge family labelled by tenant plus any extra dimensions."""
        family = GaugeMetricFamily(
            f"{_PREFIX}_{name}", documentation, labels=["tenant", *extra_labels]
        )
        families.append(family)
        return family

    pending = gauge("approvals_pending", "Approval requests awaiting a decision.")
    pending.add_metric([tenant_id], snapshot.approvals_pending)

    stalled = gauge(
        "approvals_pending_over_threshold",
        "Pending approval requests waiting longer than the threshold.",
        ("threshold",),
    )
    stalled.add_metric(
        [tenant_id, f"{threshold_hours:g}h"], snapshot.approvals_pending_over_threshold
    )

    oldest = gauge(
        "approval_pending_age_seconds_max",
        "How long the longest-waiting pending approval has been waiting.",
    )
    oldest.add_metric([tenant_id], snapshot.approval_pending_age_seconds_max)

    active = gauge("workflow_executions_active", "Workflow runs currently in progress.")
    active.add_metric([tenant_id], snapshot.executions_active)

    finished = gauge(
        "workflow_executions_finished_today",
        "Workflow runs that finished today, by terminal status.",
        ("status",),
    )
    for status, count in snapshot.executions_finished_today.items():
        finished.add_metric([tenant_id, status], count)

    decided = gauge(
        "approvals_decided_today",
        "Approval requests decided today, by decision.",
        ("decision",),
    )
    for decision, count in snapshot.approvals_decided_today.items():
        decided.add_metric([tenant_id, decision], count)

    failed_runs = gauge(
        "workflow_executions_failed_recently",
        "Workflow runs that finished in failure within the recent window.",
        ("window",),
    )
    failed_runs.add_metric([tenant_id, recent], snapshot.executions_failed_recently)

    failed_tasks = gauge(
        "workflow_tasks_failed_recently",
        "Workflow tasks that failed within the recent window, by cause.",
        ("window", "error_kind"),
    )
    for error_kind, count in snapshot.tasks_failed_recently.items():
        failed_tasks.add_metric([tenant_id, recent, error_kind], count)

    started = gauge(
        "workflow_executions_started_recently",
        "Workflow runs started within the recent window, by workflow.",
        ("window", "workflow"),
    )
    for workflow, count in snapshot.executions_started_recently.items():
        started.add_metric([tenant_id, recent, workflow], count)

    lead_time = gauge(
        "workflow_execution_lead_time_seconds_avg",
        "Mean start-to-finish duration of runs finishing in the recent window.",
        ("window", "workflow"),
    )
    for workflow, seconds in snapshot.lead_time_seconds_avg_recently.items():
        lead_time.add_metric([tenant_id, recent, workflow], seconds)

    email_depth = gauge(
        "email_queue_depth",
        "Notification emails in the outgoing queue, by delivery status.",
        ("status",),
    )
    for status, count in snapshot.email_queue_depth.items():
        email_depth.add_metric([tenant_id, status], count)

    email_age = gauge(
        "email_queue_oldest_pending_age_seconds",
        "How long the longest-waiting undelivered notification email has waited.",
    )
    email_age.add_metric([tenant_id], snapshot.email_queue_oldest_pending_age_seconds)

    registry = CollectorRegistry()
    registry.register(_SnapshotCollector(families))
    return generate_latest(registry).decode("utf-8")


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    responses={200: {"content": {CONTENT_TYPE_LATEST: {}}}},
)
async def workflow_metrics(
    service: MetricsServiceDep,
    tenant_id: CurrentTenantIdDep,
    threshold: BacklogThresholdDep,
) -> PlainTextResponse:
    """Return the tenant's workflow operations KPIs in Prometheus exposition format.

    Deliberately outside the ``ApiResponse`` envelope, like ``/health`` and
    ``/agent``: a Prometheus scraper expects the exposition text and nothing
    else. Access to this route is excluded from the uvicorn access log (see
    ``infrastructure.logging_context``) since it is polled frequently.
    """
    snapshot = await service.snapshot(threshold_hours=threshold.threshold_hours)
    body = _render(snapshot, tenant_id, threshold.threshold_hours)
    return PlainTextResponse(content=body, media_type=CONTENT_TYPE_LATEST)
