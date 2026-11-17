import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LeadTimeBucket } from "@/lib/api";
import { LeadTimeChart } from "./lead-time-chart";

const BUCKETS: LeadTimeBucket[] = [
  { bucketStart: "2026-10-01T12:00:00Z", count: 2, avgLeadTimeSeconds: 3_600 },
  { bucketStart: "2026-10-02T12:00:00Z", count: 0, avgLeadTimeSeconds: null },
  { bucketStart: "2026-10-03T12:00:00Z", count: 1, avgLeadTimeSeconds: 7_200 },
];

describe("LeadTimeChart", () => {
  it("says so when no run finished in the range", () => {
    render(<LeadTimeChart buckets={[{ ...BUCKETS[1] }]} />);
    expect(screen.getByText("No runs finished")).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("joins the days that have a reading and skips the empty ones", () => {
    const { container } = render(<LeadTimeChart buckets={BUCKETS} />);
    // 600px default width, 200px tall, peak = 7200s * 1.15 headroom.
    expect(container.querySelector("path.animate-draw-in")?.getAttribute("d")).toBe(
      "M0.0 113.0L600.0 26.1"
    );
  });

  it("reads out the latest day and steps through the days with the arrow keys", () => {
    render(<LeadTimeChart buckets={BUCKETS} />);
    const chart = screen.getByRole("slider", { name: /Lead time by day/ });
    expect(chart).toHaveAttribute("aria-valuenow", "2");
    expect(chart.getAttribute("aria-valuetext")).toContain("2h, 1 run finished");

    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(chart).toHaveAttribute("aria-valuenow", "1");
    expect(chart.getAttribute("aria-valuetext")).toContain("No runs finished");

    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(chart).toHaveAttribute("aria-valuenow", "0");
    expect(chart.getAttribute("aria-valuetext")).toContain("1h, 2 runs finished");
  });
});
