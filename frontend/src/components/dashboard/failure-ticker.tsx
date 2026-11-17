/** @module FailureTicker — Runs needing triage, in a strip along the dashboard's lower edge. */
"use client";

import { TriangleAlert } from "lucide-react";
import Link from "next/link";
import { formatRelativeTime } from "@/components/ui/date-time";
import { useT } from "@/i18n/provider";
import { translateStatus } from "@/i18n/translate";
import type { FailedExecutionEntry } from "@/lib/api";

/** Seconds each run stays on screen; the loop slows as the list grows. */
const SECONDS_PER_ITEM = 7;

/** Props for {@link FailureTicker}. */
export interface FailureTickerProps {
  /** Runs with failed tasks, newest failure first. */
  entries: FailedExecutionEntry[];
}

/**
 * The runs with failed tasks. Each item links to its run and names the first
 * failed task's cause and how long ago it failed.
 *
 * In the standard look this is a strip that scrolls by hand. On the console
 * (the `console:` variant) it is a ticker: the list is rendered twice so the
 * slide loops without a seam, the second copy hidden from assistive technology
 * and from the tab order. The slide pauses while the pointer or keyboard focus
 * is on it, and under reduced motion the console falls back to the hand-
 * scrolled strip too. Renders nothing when there are no failures.
 */
export function FailureTicker({ entries }: FailureTickerProps) {
  const t = useT();
  if (entries.length === 0) return null;

  const items = (duplicate: boolean) =>
    entries.map((entry) => {
      const task = entry.failedTasks[0];
      return (
        <li key={entry.executionId} className="shrink-0">
          <Link
            href={`/workflow-executions/${entry.executionId}`}
            tabIndex={duplicate ? -1 : undefined}
            className="flex items-center gap-2 rounded-md px-1 text-sm text-on-surface hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            <span className="font-medium">{entry.name}</span>
            {task && (
              <span className="text-on-surface-variant">
                {translateStatus(task.errorKind ?? "unclassified", t)}
                {" · "}
                {formatRelativeTime(task.failedAt, t)}
              </span>
            )}
          </Link>
        </li>
      );
    });

  return (
    <section
      aria-label={t("dashboard.needsAttention")}
      className="console-panel flex items-center gap-4 overflow-hidden py-3 pl-4"
    >
      <h2 className="flex shrink-0 items-center gap-2 text-sm font-semibold text-on-surface">
        <TriangleAlert size={16} strokeWidth={1.8} aria-hidden="true" className="text-error" />
        {t("dashboard.needsAttention")}
      </h2>
      <div className="min-w-0 flex-1 console:motion-safe:[mask-image:linear-gradient(90deg,transparent,#000_2rem,#000_calc(100%-2rem),transparent)] overflow-x-auto console:motion-safe:overflow-hidden">
        <div
          className="flex w-max console:animate-ticker hover:[animation-play-state:paused] focus-within:[animation-play-state:paused]"
          style={{ animationDuration: `${entries.length * SECONDS_PER_ITEM}s` }}
        >
          <ul className="flex shrink-0 gap-8 pr-8">{items(false)}</ul>
          <ul aria-hidden="true" className="hidden shrink-0 gap-8 pr-8 console:motion-safe:flex">
            {items(true)}
          </ul>
        </div>
      </div>
    </section>
  );
}
