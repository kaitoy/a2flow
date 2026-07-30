/** @module DateTime — Shared timestamp display showing relative time with an absolute hover tooltip. */
"use client";

import { Tooltip, type TooltipPlacement } from "./tooltip";

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

/**
 * Format an ISO timestamp as a short relative time such as "5m ago" or "2d ago".
 *
 * Used where a timestamp is glanced at rather than read precisely — notification
 * rows in the toolbar dropdown and in the profile's notification list. Pair it
 * with {@link formatFullTimestamp} in a tooltip so the exact time stays
 * available. Anything a week or older falls back to a locale date, since "9d
 * ago" stops being easier to place than the date itself.
 *
 * @param value - ISO timestamp string.
 * @returns The relative time, or an empty string when `value` is not a valid date.
 */
export function formatRelativeTime(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
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
 * Render a timestamp as short relative time (e.g. "5m ago"), with a hover/focus
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
  const display = formatRelativeTime(value);
  const full = formatFullTimestamp(value);
  return (
    <Tooltip label={full} placement={placement}>
      <time dateTime={date.toISOString()} className={cls}>
        {display}
      </time>
    </Tooltip>
  );
}
