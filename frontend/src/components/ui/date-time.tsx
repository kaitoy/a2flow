/** @module DateTime — Shared timestamp display with an absolute, hover tooltip. */
"use client";

import { Tooltip, type TooltipPlacement } from "./tooltip";

/** Compact display format: medium date plus hour/minute, e.g. "Jun 14, 2026, 3:45 PM". */
const DISPLAY_FORMAT: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" };

/** Parts used to assemble the full timestamp as `YYYY/MM/DD HH:mm:ss TZ`. */
const FULL_FORMAT = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  timeZoneName: "short",
});

/**
 * Format an ISO timestamp as `YYYY/MM/DD HH:mm:ss TZ` in the local time zone,
 * e.g. "2026/06/14 08:42:06 JST", including seconds and the short time-zone name.
 *
 * @param value - ISO timestamp string.
 * @returns The full timestamp, or an empty string when `value` is not a valid date.
 */
export function formatFullTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = FULL_FORMAT.formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}/${get("month")}/${get("day")} ${get("hour")}:${get("minute")}:${get("second")} ${get("timeZoneName")}`;
}

/** Props for {@link DateTime}. */
export interface DateTimeProps {
  /** ISO timestamp to render. */
  value: string;
  /** Side of the trigger the tooltip should appear on. Defaults to `top`. */
  placement?: TooltipPlacement;
  /** Extra classes merged after the built-in `font-mono` on the `<time>` element. */
  className?: string;
}

/**
 * Render a timestamp showing the date down to the minute, with a hover/focus
 * tooltip revealing the full timestamp including seconds and time zone. Invalid
 * values render an em dash with no tooltip. Timestamps are machine-formatted
 * data, so they render in the mono data face (JetBrains Mono) per DESIGN.md;
 * the size is inherited from the caller.
 */
export function DateTime({ value, placement = "top", className }: DateTimeProps) {
  const cls = ["font-mono", className].filter(Boolean).join(" ");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return <span className={cls}>—</span>;
  }
  const display = date.toLocaleString(undefined, DISPLAY_FORMAT);
  const full = formatFullTimestamp(value);
  return (
    <Tooltip label={full} placement={placement}>
      <time dateTime={date.toISOString()} className={cls}>
        {display}
      </time>
    </Tooltip>
  );
}
