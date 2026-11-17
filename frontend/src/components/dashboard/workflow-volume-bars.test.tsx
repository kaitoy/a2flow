import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkflowVolumeBars } from "./workflow-volume-bars";

describe("WorkflowVolumeBars", () => {
  it("says so when no run started in the range", () => {
    render(<WorkflowVolumeBars entries={[]} />);
    expect(screen.getByText("No runs started in this range.")).toBeInTheDocument();
  });

  it("draws one bar per workflow, sized against the busiest, with a segment per outcome present", () => {
    render(
      <WorkflowVolumeBars
        entries={[
          {
            workflowId: "w1",
            workflowName: "Invoices",
            total: 10,
            running: 2,
            completed: 7,
            failed: 1,
            avgLeadTimeSeconds: 5_400,
          },
          {
            workflowId: null,
            workflowName: "Onboarding",
            total: 5,
            running: 0,
            completed: 5,
            failed: 0,
            avgLeadTimeSeconds: null,
          },
        ]}
      />
    );
    const [invoices, onboarding] = screen.getAllByRole("listitem");
    expect(invoices).toHaveTextContent("Invoices");
    expect(invoices).toHaveTextContent("avg 1.5h · 10");
    expect(screen.getByTitle("completed: 7")).toHaveStyle({ flexGrow: "7" });
    expect(screen.getByTitle("failed: 1")).toBeInTheDocument();
    expect(screen.getByTitle("running: 2")).toHaveClass("console:animate-flow-stripes");

    // Half the busiest workflow's runs, and only the one outcome it has.
    expect(onboarding.querySelector("[style*='width']")).toHaveStyle({ width: "50%" });
    expect(onboarding.querySelectorAll("[title]")).toHaveLength(1);
    expect(onboarding).not.toHaveTextContent("avg");
  });
});
