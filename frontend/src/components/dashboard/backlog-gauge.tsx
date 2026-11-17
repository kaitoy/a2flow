/** @module BacklogGauge — How much of the approval backlog is stalled, and who holds it. */
"use client";

import { useT } from "@/i18n/provider";
import type { ApprovalBacklogEntry } from "@/lib/api";
import { formatDuration } from "@/lib/format-duration";

/** Share of the ring left empty between its two arcs, so they read as two marks. */
const ARC_GAP = 1.5;

/** Props for {@link BacklogGauge}. */
export interface BacklogGaugeProps {
  /** Approvals awaiting a decision. */
  pending: number;
  /** Of `pending`, those waiting longer than the stalled threshold (24 hours). */
  overThreshold: number;
  /** How long the longest-waiting approval has waited, in seconds. */
  oldestSeconds: number;
  /** The backlog's groups, longest single wait first. */
  entries: ApprovalBacklogEntry[];
  /** Display names for the entries whose `groupKind` is `"user"`, keyed by user id. */
  userNames: Map<string, string>;
}

/**
 * The approval backlog as a radial gauge over a ranked list.
 *
 * The ring is the whole backlog: the amber arc is the share stalled past the
 * threshold, the accent arc the share still within it. On the console (the
 * `console:` variant) the arcs glow and a radar sweep turns inside. Below, each approver (or workflow) gets a bar sized by its
 * longest single wait — amber once any of its approvals is stalled.
 */
export function BacklogGauge({
  pending,
  overThreshold,
  oldestSeconds,
  entries,
  userNames,
}: BacklogGaugeProps) {
  const t = useT();
  const stalledShare = pending > 0 ? (overThreshold / pending) * 100 : 0;
  const onTimeShare = pending > 0 ? 100 - stalledShare : 0;
  const gap = stalledShare > 0 && onTimeShare > 0 ? ARC_GAP : 0;
  const longest = Math.max(1, ...entries.map((e) => e.maxWaitSeconds));

  const nameOf = (entry: ApprovalBacklogEntry) =>
    entry.groupKind === "user" && entry.groupId
      ? (userNames.get(entry.groupId) ?? entry.groupId)
      : (entry.groupLabel ?? t("dashboard.unassigned"));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-5">
        <div className="relative size-36 shrink-0">
          {/* The radar: a wedge of light turning inside the ring. Console only. */}
          <div
            aria-hidden="true"
            className="absolute inset-4 hidden rounded-full opacity-70 console:block console:animate-console-radar"
            style={{
              background:
                "conic-gradient(from var(--live-angle), transparent 0deg, transparent 290deg, color-mix(in oklab, var(--color-accent) 42%, transparent) 360deg)",
            }}
          />
          <svg viewBox="0 0 144 144" aria-hidden="true" className="absolute inset-0 -rotate-90">
            <circle
              cx="72"
              cy="72"
              r="62"
              fill="none"
              stroke="var(--color-glass-strong)"
              strokeWidth="10"
            />
            {onTimeShare > 0 && (
              <circle
                cx="72"
                cy="72"
                r="62"
                fill="none"
                pathLength="100"
                stroke="var(--color-accent)"
                strokeWidth="10"
                strokeDasharray={`${onTimeShare - gap} 100`}
                className="console:[filter:drop-shadow(0_0_5px_var(--color-accent))]"
              />
            )}
            {stalledShare > 0 && (
              <circle
                cx="72"
                cy="72"
                r="62"
                fill="none"
                pathLength="100"
                stroke="var(--c-tag-amber)"
                strokeWidth="10"
                strokeDasharray={`${stalledShare - gap} 100`}
                strokeDashoffset={-onTimeShare}
                className="console:[filter:drop-shadow(0_0_5px_var(--c-tag-amber))]"
              />
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="console:glow-text font-mono text-4xl font-semibold leading-none tabular-nums text-on-surface">
              {pending}
            </span>
            <span className="mt-1 text-xs text-on-surface-variant">{t("dashboard.pending")}</span>
          </div>
        </div>
        <dl className="flex min-w-0 flex-col gap-3 text-sm">
          <div>
            <dt className="flex items-center gap-2 text-xs text-on-surface-variant">
              <span aria-hidden="true" className="size-2 rounded-full bg-(--c-tag-amber)" />
              {t("dashboard.waitingOver24h")}
            </dt>
            <dd className="font-mono text-xl font-semibold tabular-nums text-on-surface">
              {overThreshold}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-on-surface-variant">{t("dashboard.longestWait")}</dt>
            <dd className="font-mono text-xl font-semibold tabular-nums text-on-surface">
              {pending > 0 ? formatDuration(oldestSeconds, t.locale) : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {entries.length === 0 ? (
        <p className="text-sm text-on-surface-variant">{t("dashboard.noPendingApprovals")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {entries.map((entry) => (
            <li key={`${entry.groupKind}:${entry.groupId}`} className="min-w-0">
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate text-on-surface">{nameOf(entry)}</span>
                <span className="shrink-0 font-mono text-xs tabular-nums text-on-surface-variant">
                  {t("dashboard.pendingCount", { count: entry.pending })}
                  {" · "}
                  {formatDuration(entry.maxWaitSeconds, t.locale)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-full bg-glass-strong">
                <div
                  className="h-full origin-left rounded-full animate-grow-x"
                  style={{
                    width: `${Math.max(2, (entry.maxWaitSeconds / longest) * 100)}%`,
                    background:
                      entry.overThreshold > 0 ? "var(--c-tag-amber)" : "var(--color-accent)",
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
