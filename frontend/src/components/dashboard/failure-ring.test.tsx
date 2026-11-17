import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FailureRing } from "./failure-ring";

describe("FailureRing", () => {
  it("gives the all-clear when nothing failed", () => {
    const { container } = render(<FailureRing counts={{ timeout: 0 }} />);
    expect(screen.getByText("No task has failed in the last 24 hours.")).toBeInTheDocument();
    expect(container.querySelector("circle[pathLength]")).toBeNull();
  });

  it("totals the failures and lists each cause present, in the fixed kind order", () => {
    const { container } = render(
      <FailureRing counts={{ unclassified: 1, timeout: 1, api_error: 2 }} />
    );
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "api error2",
      "timeout1",
      "unclassified1",
    ]);
    // Each kind keeps its own color whichever kinds are present.
    expect(
      [...container.querySelectorAll("circle[pathLength]")].map((segment) =>
        segment.getAttribute("stroke")
      )
    ).toEqual(["var(--kind-api-error)", "var(--kind-timeout)", "var(--kind-unclassified)"]);
  });
});
