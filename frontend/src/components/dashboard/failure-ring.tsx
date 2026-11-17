/** @module FailureRing — Why tasks failed in the last 24 hours, as a donut. */
"use client";

import { CircleCheck } from "lucide-react";
import type { CSSProperties } from "react";
import { useT } from "@/i18n/provider";
import { translateStatus } from "@/i18n/translate";

/**
 * Every task error kind in the backend's declaration order, plus the
 * `unclassified` bucket for failures the agent did not classify. The order is
 * fixed so a kind keeps its color and its place whichever kinds are present.
 */
const KINDS = [
  "api_error",
  "timeout",
  "script_error",
  "invalid_input",
  "permission_denied",
  "rejected",
  "other",
  "unclassified",
] as const;

/** Share of the ring left empty after each segment. */
const SEGMENT_GAP = 1.5;

/** Props for {@link FailureRing}. */
export interface FailureRingProps {
  /** Failed-task counts keyed by error kind (`MetricsSummary.tasksFailedRecently`). */
  counts: Record<string, number>;
}

/**
 * Failed tasks by cause: a donut whose segments are the error kinds, around
 * the total — with a breathing halo behind it on the console (the `console:`
 * variant). The legend beside it names every kind present and its count. With no failures the ring
 * gives way to an all-clear line.
 */
export function FailureRing({ counts }: FailureRingProps) {
  const t = useT();
  const segments = KINDS.map((kind) => ({ kind, count: counts[kind] ?? 0 })).filter(
    (segment) => segment.count > 0
  );
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);

  if (total === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-on-surface-variant">
        <CircleCheck size={18} strokeWidth={1.8} aria-hidden="true" className="text-success" />
        {t("dashboard.noFailures")}
      </p>
    );
  }

  const gap = segments.length > 1 ? SEGMENT_GAP : 0;
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative size-36 shrink-0">
        <div
          aria-hidden="true"
          className="absolute inset-7 hidden rounded-full bg-error/25 blur-md console:block console:animate-console-pulse"
        />
        <svg viewBox="0 0 144 144" aria-hidden="true" className="absolute inset-0 -rotate-90">
          {segments.map((segment) => {
            const share = (segment.count / total) * 100;
            const dashoffset = -offset;
            offset += share;
            return (
              <circle
                key={segment.kind}
                cx="72"
                cy="72"
                r="60"
                fill="none"
                pathLength="100"
                stroke={`var(--kind-${segment.kind.replaceAll("_", "-")})`}
                strokeWidth="14"
                strokeDasharray={`${Math.max(0.5, share - gap)} 100`}
                strokeDashoffset={dashoffset}
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="console:glow-text font-mono text-4xl font-semibold leading-none tabular-nums text-on-surface"
            style={{ "--glow": "var(--color-error)" } as CSSProperties}
          >
            {total}
          </span>
          <span className="mt-1 text-xs text-on-surface-variant">{t("dashboard.failedTasks")}</span>
        </div>
      </div>
      <ul className="flex w-full flex-col gap-2 text-sm">
        {segments.map((segment) => (
          <li key={segment.kind} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="size-2.5 shrink-0 rounded-sm"
              style={{ backgroundColor: `var(--kind-${segment.kind.replaceAll("_", "-")})` }}
            />
            <span className="truncate text-on-surface">{translateStatus(segment.kind, t)}</span>
            <span className="ml-auto font-mono tabular-nums text-on-surface-variant">
              {segment.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
