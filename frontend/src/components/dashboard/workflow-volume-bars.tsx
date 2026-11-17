/** @module WorkflowVolumeBars — Runs per workflow, split by how they ended. */
"use client";

import { useT } from "@/i18n/provider";
import { translateStatus } from "@/i18n/translate";
import type { WorkflowVolumeEntry } from "@/lib/api";
import { formatDuration } from "@/lib/format-duration";

/** The three outcomes a bar is split into, in drawing order, with their series color. */
const SEGMENTS = [
  { key: "completed", color: "var(--series-ok)" },
  { key: "failed", color: "var(--series-fail)" },
  { key: "running", color: "var(--series-run)" },
] as const;

/** Props for {@link WorkflowVolumeBars}. */
export interface WorkflowVolumeBarsProps {
  /** Per-workflow volume, busiest first. */
  entries: WorkflowVolumeEntry[];
}

/**
 * One stacked bar per workflow, its length the run count relative to the
 * busiest workflow, split into completed, failed and still-running runs. The
 * running segment is striped — those runs are still moving — and on the
 * console (the `console:` variant) the stripes slide.
 *
 * Each row states its total and average lead time in text, and each segment
 * names itself and its count on hover, so no value is carried by color alone.
 */
export function WorkflowVolumeBars({ entries }: WorkflowVolumeBarsProps) {
  const t = useT();
  if (entries.length === 0) {
    return <p className="text-sm text-on-surface-variant">{t("dashboard.noRuns")}</p>;
  }
  const busiest = Math.max(1, ...entries.map((e) => e.total));

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-3.5">
        {entries.map((entry) => (
          <li key={entry.workflowId ?? entry.workflowName} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate text-on-surface">{entry.workflowName}</span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-on-surface-variant">
                {entry.avgLeadTimeSeconds != null &&
                  `${t("dashboard.avgLeadTime", {
                    duration: formatDuration(entry.avgLeadTimeSeconds, t.locale),
                  })} · `}
                <span className="text-sm font-semibold text-on-surface">{entry.total}</span>
              </span>
            </div>
            <div
              className="mt-1.5 flex h-3 origin-left gap-0.5 animate-grow-x"
              style={{ width: `${Math.max(3, (entry.total / busiest) * 100)}%` }}
            >
              {SEGMENTS.filter((segment) => entry[segment.key] > 0).map((segment) => (
                <div
                  key={segment.key}
                  title={`${translateStatus(segment.key, t)}: ${entry[segment.key]}`}
                  className={[
                    "h-full min-w-1 rounded-sm",
                    segment.key === "running"
                      ? "console:animate-flow-stripes bg-[repeating-linear-gradient(115deg,transparent_0_6px,oklch(1_0_0/0.28)_6px_12px)] [background-size:24px_100%]"
                      : "",
                  ].join(" ")}
                  style={{ flexGrow: entry[segment.key], backgroundColor: segment.color }}
                />
              ))}
            </div>
          </li>
        ))}
      </ul>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-on-surface-variant">
        {SEGMENTS.map((segment) => (
          <li key={segment.key} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: segment.color }}
            />
            {translateStatus(segment.key, t)}
          </li>
        ))}
      </ul>
    </div>
  );
}
