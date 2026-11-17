/**
 * @module useDashboardMetrics — polls the operations metrics behind `/dashboard`.
 *
 * One tick reads every panel's data in parallel and keeps whatever it last
 * read when a request fails, so an outage dims the "live" indicator instead of
 * blanking the screen.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type ApprovalBacklogEntry,
  type FailedExecutionEntry,
  getApprovalBacklog,
  getLeadTimeTrend,
  getMetricsSummary,
  getWorkflowVolume,
  type LeadTimeBucket,
  listFailedExecutions,
  type MetricsSummary,
  type WorkflowVolumeEntry,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppSelector } from "@/store/hooks";

/** How often the dashboard re-reads its metrics. */
export const DASHBOARD_POLL_MS = 15_000;

/** How many past summaries are kept for the KPI tiles' sparklines. */
const HISTORY_LENGTH = 40;

/** Which key the approval backlog is grouped by. */
export type BacklogAxis = "approver" | "workflow";

/** Everything the dashboard renders, plus the state of the polling loop. */
export interface DashboardMetrics {
  /** The single-value KPIs, or `null` until the first read lands. */
  summary: MetricsSummary | null;
  /** Past summaries, oldest first, sampled once per poll while the page is open. */
  history: MetricsSummary[];
  /** Per-workflow run volume over the selected range, busiest first. */
  volume: WorkflowVolumeEntry[];
  /** Daily average lead time over the selected range, oldest first. */
  trend: LeadTimeBucket[];
  /** Pending-approval backlog on the selected axis, longest wait first. */
  backlog: ApprovalBacklogEntry[];
  /** Runs with failed tasks, newest first. Always empty for a non-admin. */
  failures: FailedExecutionEntry[];
  /** True when the most recent poll could not read the KPIs. */
  stale: boolean;
  /** `Date.now()` of the last successful KPI read, or `null` before the first. */
  updatedAt: number | null;
  /** False while a platform-scoped user has not picked a tenant to act as. */
  tenantReady: boolean;
  /** Poll once now, restarting the interval. */
  refresh: () => void;
}

/**
 * Poll the operations metrics every {@link DASHBOARD_POLL_MS}.
 *
 * Polling pauses while the tab is hidden and resumes with an immediate read
 * when it becomes visible again. The failure list is requested only for an
 * `admin`, the one role the backend serves it to.
 *
 * @param rangeDays - Length of the window for the volume, trend, and failure views.
 * @param backlogAxis - Grouping of the approval backlog.
 * @returns The latest data and the loop's state.
 */
export function useDashboardMetrics(rangeDays: number, backlogAxis: BacklogAxis): DashboardMetrics {
  const user = useAppSelector((s) => s.auth.user);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantReady = user == null || user.tenantId != null || selectedTenantId != null;
  const tenantKey = selectedTenantId ?? user?.tenantId ?? null;
  const isAdmin = useHasRole(Role.ADMIN);

  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [history, setHistory] = useState<MetricsSummary[]>([]);
  const [volume, setVolume] = useState<WorkflowVolumeEntry[]>([]);
  const [trend, setTrend] = useState<LeadTimeBucket[]>([]);
  const [backlog, setBacklog] = useState<ApprovalBacklogEntry[]>([]);
  const [failures, setFailures] = useState<FailedExecutionEntry[]>([]);
  const [stale, setStale] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);

  // A sparkline that mixed two tenants' samples would draw a cliff that never happened.
  // biome-ignore lint/correctness/useExhaustiveDependencies: tenantKey is the trigger, not an input
  useEffect(() => {
    setSummary(null);
    setHistory([]);
  }, [tenantKey]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: nonce and tenantKey restart the loop
  useEffect(() => {
    if (!tenantReady) return;
    let active = true;

    const tick = async () => {
      if (document.hidden) return;
      const since = new Date(Date.now() - rangeDays * 86_400_000).toISOString();
      // ponytail: one cadence for every panel. The 30-day views change slowly;
      // give them their own slower interval if these reads ever show up in load.
      const [nextSummary, nextVolume, nextTrend, nextBacklog, nextFailures] =
        await Promise.allSettled([
          getMetricsSummary(),
          getWorkflowVolume(since, 8),
          getLeadTimeTrend(since),
          getApprovalBacklog(backlogAxis, 5),
          isAdmin ? listFailedExecutions(since, 20) : Promise.resolve([]),
        ]);
      if (!active) return;
      if (nextSummary.status === "fulfilled") {
        setSummary(nextSummary.value);
        setHistory((past) => [...past, nextSummary.value].slice(-HISTORY_LENGTH));
        setUpdatedAt(Date.now());
      }
      setStale(nextSummary.status === "rejected");
      if (nextVolume.status === "fulfilled") setVolume(nextVolume.value);
      if (nextTrend.status === "fulfilled") setTrend(nextTrend.value);
      if (nextBacklog.status === "fulfilled") setBacklog(nextBacklog.value);
      if (nextFailures.status === "fulfilled") setFailures(nextFailures.value);
    };

    void tick();
    const id = setInterval(() => void tick(), DASHBOARD_POLL_MS);
    const onVisible = () => {
      if (!document.hidden) void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [rangeDays, backlogAxis, isAdmin, tenantReady, tenantKey, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return {
    summary,
    history,
    volume,
    trend,
    backlog,
    failures,
    stale,
    updatedAt,
    tenantReady,
    refresh,
  };
}
