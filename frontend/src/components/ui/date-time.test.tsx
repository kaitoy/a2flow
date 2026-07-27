import { afterEach, describe, expect, it, vi } from "vitest";
import { formatFullTimestamp, formatRelativeTime } from "./date-time";

/** Fixed "now" the relative-time cases are measured against. */
const NOW = new Date("2026-06-14T12:00:00Z");

/** ISO timestamp for a moment `ms` milliseconds before {@link NOW}. */
function ago(ms: number): string {
  return new Date(NOW.getTime() - ms).toISOString();
}

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("formatRelativeTime", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function freeze() {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  }

  it("reports anything under a minute as 'just now'", () => {
    freeze();
    expect(formatRelativeTime(ago(0))).toBe("just now");
    expect(formatRelativeTime(ago(59 * SECOND))).toBe("just now");
  });

  it("reports minutes up to an hour", () => {
    freeze();
    expect(formatRelativeTime(ago(MINUTE))).toBe("1m ago");
    expect(formatRelativeTime(ago(59 * MINUTE))).toBe("59m ago");
  });

  it("reports hours up to a day", () => {
    freeze();
    expect(formatRelativeTime(ago(HOUR))).toBe("1h ago");
    expect(formatRelativeTime(ago(23 * HOUR))).toBe("23h ago");
  });

  it("reports days up to a week", () => {
    freeze();
    expect(formatRelativeTime(ago(DAY))).toBe("1d ago");
    expect(formatRelativeTime(ago(6 * DAY))).toBe("6d ago");
  });

  it("falls back to a locale date from a week out", () => {
    freeze();
    const iso = ago(7 * DAY);
    expect(formatRelativeTime(iso)).toBe(new Date(iso).toLocaleDateString());
  });

  it("clamps future timestamps to 'just now' rather than reporting negative time", () => {
    freeze();
    expect(formatRelativeTime(new Date(NOW.getTime() + HOUR).toISOString())).toBe("just now");
  });

  it("returns an empty string for an unparseable value", () => {
    expect(formatRelativeTime("not a date")).toBe("");
  });
});

describe("formatFullTimestamp", () => {
  it("renders date, time to the second, and the zone name", () => {
    expect(formatFullTimestamp("2026-06-14T08:42:06Z")).toMatch(
      /^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2} .+$/
    );
  });

  it("returns an empty string for an unparseable value", () => {
    expect(formatFullTimestamp("not a date")).toBe("");
  });
});
