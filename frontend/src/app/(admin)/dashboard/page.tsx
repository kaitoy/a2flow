/**
 * @module DashboardPage — The tenant's workflow operations metrics, live, in
 * the app's standard look or as the always-dark "Mission Control" console.
 */
"use client";

import {
  Activity,
  Building2,
  CircleCheckBig,
  Hourglass,
  LayoutDashboard,
  Mail,
  Maximize,
  Minimize,
  OctagonAlert,
  Radar,
  RefreshCw,
  Unplug,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { BacklogGauge } from "@/components/dashboard/backlog-gauge";
import { ConsoleFrame, ConsolePanel } from "@/components/dashboard/console-panel";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { FailureRing } from "@/components/dashboard/failure-ring";
import { FailureTicker } from "@/components/dashboard/failure-ticker";
import { KpiTile } from "@/components/dashboard/kpi-tile";
import { LeadTimeChart } from "@/components/dashboard/lead-time-chart";
import { WorkflowVolumeBars } from "@/components/dashboard/workflow-volume-bars";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useDashboardLook } from "@/hooks/useDashboardLook";
import {
  type BacklogAxis,
  DASHBOARD_POLL_MS,
  useDashboardMetrics,
} from "@/hooks/useDashboardMetrics";
import { useUserNames } from "@/hooks/useNames";
import { useT } from "@/i18n/provider";
import { formatDuration } from "@/lib/format-duration";

/** The selectable lengths, in days, of the window behind the range-bound panels. */
const RANGES = ["7", "30", "90"] as const;
type Range = (typeof RANGES)[number];

/** An undelivered email older than this turns the queue tile amber. */
const EMAIL_SLOW_SECONDS = 300;

/** Sum the values of a label-to-count mapping. */
function total(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0);
}

/**
 * The operations dashboard at `/dashboard`.
 *
 * Five KPI tiles over four charts and, for an admin, a strip of the runs
 * needing triage. Everything re-reads itself every {@link DASHBOARD_POLL_MS},
 * and the dashboard can be sent full screen for a wall display.
 *
 * It has two looks, switched from the header and remembered per browser by
 * {@link useDashboardLook}. The standard look obeys the design system like
 * every other screen. Mission Control is the one place exempt from its "quiet
 * until it flows" rule — see DESIGN.md → Mission Control.
 */
export default function DashboardPage() {
  const t = useT();
  const [range, setRange] = useState<Range>("30");
  const [axis, setAxis] = useState<BacklogAxis>("approver");
  const [look, setLook] = useDashboardLook();
  const metrics = useDashboardMetrics(Number(range), axis);
  const { summary, history } = metrics;

  const frameRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === frameRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void frameRef.current?.requestFullscreen();
  };

  const userNames = useUserNames(
    metrics.backlog.filter((entry) => entry.groupKind === "user").map((entry) => entry.groupId)
  );

  const finished = metrics.trend.reduce((sum, bucket) => sum + bucket.count, 0);
  const averageLeadTime =
    finished > 0
      ? metrics.trend.reduce(
          (sum, bucket) => sum + (bucket.avgLeadTimeSeconds ?? 0) * bucket.count,
          0
        ) / finished
      : null;

  return (
    <ConsoleFrame ref={frameRef} look={look}>
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex items-center gap-4">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface">
            {t("common.dashboard")}
          </h1>
          {metrics.tenantReady && (
            <LiveIndicator stale={metrics.stale} updatedAt={metrics.updatedAt} />
          )}
        </div>
        <div className="flex items-center gap-2">
          <SegmentedControl<Range>
            aria-label={t("dashboard.timeRange")}
            value={range}
            onChange={setRange}
            options={RANGES.map((days) => ({
              value: days,
              label: t("dashboard.lastDays", { count: Number(days) }),
            }))}
          />
          <HeaderIconButton label={t("admin.refresh")} onClick={metrics.refresh}>
            <RefreshCw size={18} strokeWidth={1.8} aria-hidden="true" />
          </HeaderIconButton>
          <HeaderIconButton
            label={
              look === "console"
                ? t("dashboard.switchToStandardLook")
                : t("dashboard.switchToConsoleLook")
            }
            onClick={() => setLook(look === "console" ? "standard" : "console")}
          >
            {look === "console" ? (
              <LayoutDashboard size={18} strokeWidth={1.8} aria-hidden="true" />
            ) : (
              <Radar size={18} strokeWidth={1.8} aria-hidden="true" />
            )}
          </HeaderIconButton>
          <HeaderIconButton
            label={fullscreen ? t("dashboard.exitFullScreen") : t("dashboard.enterFullScreen")}
            onClick={toggleFullscreen}
          >
            {fullscreen ? (
              <Minimize size={18} strokeWidth={1.8} aria-hidden="true" />
            ) : (
              <Maximize size={18} strokeWidth={1.8} aria-hidden="true" />
            )}
          </HeaderIconButton>
        </div>
      </header>

      {!metrics.tenantReady ? (
        <EmptyState icon={Building2} description={t("dashboard.selectTenant")} className="py-24" />
      ) : summary == null ? (
        metrics.stale ? (
          <EmptyState
            icon={Unplug}
            animation="wiggle"
            title={t("dashboard.connectionLost")}
            description={t("dashboard.metricsUnavailable")}
            className="py-24"
          />
        ) : (
          <DashboardSkeleton />
        )
      ) : (
        <>
          {/* Wrapping and growing, so a short last row never leaves a hole. */}
          <div className="flex flex-wrap gap-4 *:min-w-36 *:flex-1 *:basis-36">
            <KpiTile
              label={t("dashboard.activeRuns")}
              value={summary.executionsActive}
              icon={Activity}
              tone="run"
              detail={t("dashboard.startedIn24h", {
                count: total(summary.executionsStartedRecently),
              })}
              history={history.map((h) => h.executionsActive)}
            />
            <KpiTile
              label={t("dashboard.pendingApprovals")}
              value={summary.approvalsPending}
              icon={Hourglass}
              tone={summary.approvalsPendingOverThreshold > 0 ? "warn" : "accent"}
              detail={t("dashboard.decidedToday", {
                count: total(summary.approvalsDecidedToday),
              })}
              history={history.map((h) => h.approvalsPending)}
            />
            <KpiTile
              label={t("dashboard.finishedToday")}
              value={total(summary.executionsFinishedToday)}
              icon={CircleCheckBig}
              detail={
                total(summary.executionsFinishedToday) > 0
                  ? t("dashboard.completedShare", {
                      percent: new Intl.NumberFormat(t.locale, { style: "percent" }).format(
                        (summary.executionsFinishedToday.completed ?? 0) /
                          total(summary.executionsFinishedToday)
                      ),
                    })
                  : undefined
              }
              history={history.map((h) => total(h.executionsFinishedToday))}
            />
            <KpiTile
              label={t("dashboard.failedRuns24h")}
              value={summary.executionsFailedRecently}
              icon={OctagonAlert}
              tone={summary.executionsFailedRecently > 0 ? "fail" : "accent"}
              detail={t("dashboard.failedTasksCount", {
                count: total(summary.tasksFailedRecently),
              })}
              history={history.map((h) => h.executionsFailedRecently)}
            />
            <KpiTile
              label={t("dashboard.emailQueue")}
              value={
                (summary.emailQueueDepth.pending ?? 0) + (summary.emailQueueDepth.sending ?? 0)
              }
              icon={Mail}
              tone={
                (summary.emailQueueDepth.failed ?? 0) > 0
                  ? "fail"
                  : summary.emailQueueOldestPendingAgeSeconds > EMAIL_SLOW_SECONDS
                    ? "warn"
                    : "accent"
              }
              detail={
                (summary.emailQueueDepth.failed ?? 0) > 0
                  ? t("dashboard.failedToSend", { count: summary.emailQueueDepth.failed })
                  : summary.emailQueueOldestPendingAgeSeconds > 0
                    ? t("dashboard.oldestWaiting", {
                        duration: formatDuration(
                          summary.emailQueueOldestPendingAgeSeconds,
                          t.locale
                        ),
                      })
                    : t("dashboard.nothingWaiting")
              }
              history={history.map(
                (h) => (h.emailQueueDepth.pending ?? 0) + (h.emailQueueDepth.sending ?? 0)
              )}
            />
          </div>

          <div className="grid gap-4 @4xl:grid-cols-3">
            <ConsolePanel
              title={t("dashboard.leadTime")}
              hint={t("dashboard.leadTimeHint")}
              className="@4xl:col-span-2"
              aside={
                averageLeadTime != null && (
                  <p className="text-right">
                    <span className="console:glow-text block font-mono text-3xl font-semibold leading-none tabular-nums text-on-surface [--glow:var(--color-accent)]">
                      {formatDuration(averageLeadTime, t.locale)}
                    </span>
                    <span className="text-xs text-on-surface-variant">
                      {t("dashboard.averageOverRange")}
                    </span>
                  </p>
                )
              }
            >
              <LeadTimeChart buckets={metrics.trend} />
            </ConsolePanel>
            <ConsolePanel
              title={t("dashboard.approvalBacklog")}
              hint={t("dashboard.approvalBacklogHint")}
              aside={
                <SegmentedControl<BacklogAxis>
                  aria-label={t("dashboard.groupBacklogBy")}
                  value={axis}
                  onChange={setAxis}
                  options={[
                    { value: "approver", label: t("approvals.approver") },
                    { value: "workflow", label: t("workflowExecutions.workflow") },
                  ]}
                />
              }
            >
              <BacklogGauge
                pending={summary.approvalsPending}
                overThreshold={summary.approvalsPendingOverThreshold}
                oldestSeconds={summary.approvalPendingAgeSecondsMax}
                entries={metrics.backlog}
                userNames={userNames}
              />
            </ConsolePanel>
          </div>

          <div className="grid gap-4 @4xl:grid-cols-3">
            <ConsolePanel
              title={t("dashboard.runsByWorkflow")}
              hint={t("dashboard.runsByWorkflowHint")}
              className="@4xl:col-span-2"
            >
              <WorkflowVolumeBars entries={metrics.volume} />
            </ConsolePanel>
            <ConsolePanel
              title={t("dashboard.failureCauses")}
              hint={t("dashboard.failureCausesHint")}
            >
              <FailureRing counts={summary.tasksFailedRecently} />
            </ConsolePanel>
          </div>

          <FailureTicker entries={metrics.failures} />
        </>
      )}
    </ConsoleFrame>
  );
}

/**
 * The header's heartbeat: a dot and a label saying the figures are current.
 * On the console (the `console:` variant) the dot pulses inside a ring that
 * empties over one poll interval, then refills when the next reading lands.
 * When the last poll failed the dot turns amber — and on the console stops —
 * and the label says the figures on screen are the last ones read.
 */
function LiveIndicator({ stale, updatedAt }: { stale: boolean; updatedAt: number | null }) {
  const t = useT();
  return (
    <p
      role="status"
      className="flex items-center gap-2 text-sm text-on-surface-variant"
      style={{ color: stale ? "var(--c-tag-amber)" : undefined }}
    >
      <span className="relative flex size-5 items-center justify-center">
        {!stale && (
          <svg
            viewBox="0 0 20 20"
            aria-hidden="true"
            className="absolute inset-0 hidden -rotate-90 console:block"
          >
            {/* Keyed on the reading's time so the countdown restarts with each one. */}
            <circle
              key={updatedAt}
              cx="10"
              cy="10"
              r="8.5"
              fill="none"
              pathLength="100"
              strokeDasharray="100"
              stroke="var(--color-accent)"
              strokeOpacity="0.55"
              strokeWidth="1.5"
              className="console:animate-countdown"
              style={{ animationDuration: `${DASHBOARD_POLL_MS}ms` }}
            />
          </svg>
        )}
        <span
          aria-hidden="true"
          className={[
            "size-2 rounded-full",
            stale
              ? "bg-(--c-tag-amber)"
              : "bg-accent console:shadow-[0_0_10px_var(--color-accent)] console:animate-console-pulse",
          ].join(" ")}
        />
      </span>
      {stale ? t("dashboard.connectionLost") : t("dashboard.live")}
    </p>
  );
}
