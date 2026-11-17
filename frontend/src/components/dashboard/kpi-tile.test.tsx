import { render, screen } from "@testing-library/react";
import { Activity } from "lucide-react";
import { describe, expect, it } from "vitest";
import { KpiTile } from "./kpi-tile";

describe("KpiTile", () => {
  it("names itself by its label and states the settled value and the detail", () => {
    render(<KpiTile label="Active runs" value={1234} icon={Activity} detail="5 started in 24h" />);
    const tile = screen.getByRole("region", { name: "Active runs" });
    // The counting-up figure is aria-hidden; the settled value is the readable copy.
    expect(screen.getByText("1,234")).toHaveClass("sr-only");
    expect(tile).toHaveTextContent("5 started in 24h");
  });

  it("lights the tile in its tone", () => {
    render(<KpiTile label="Failed runs" value={2} icon={Activity} tone="fail" />);
    expect(
      screen.getByRole("region", { name: "Failed runs" }).style.getPropertyValue("--glow")
    ).toBe("var(--color-error)");
  });

  it("traces the history as a sparkline and falls back to a flat baseline", () => {
    const { container, rerender } = render(
      <KpiTile label="Active runs" value={3} icon={Activity} history={[1, 4, 3]} />
    );
    const trace = () => container.querySelector("path[stroke]")?.getAttribute("d");
    expect(trace()).toBe("M0.00 26.00L50.00 2.00L100.00 10.00");

    rerender(<KpiTile label="Active runs" value={3} icon={Activity} history={[3]} />);
    expect(trace()).toBe("M0.00 26.00L100.00 26.00");
  });
});
