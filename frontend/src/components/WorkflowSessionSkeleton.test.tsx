import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { WorkflowSessionSkeleton } from "./WorkflowSessionSkeleton";

describe("WorkflowSessionSkeleton", () => {
  it("exposes role=status for assistive technologies", () => {
    render(<WorkflowSessionSkeleton />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("renders three task-row placeholders in the timeline aside", () => {
    const { container } = render(<WorkflowSessionSkeleton />);
    expect(container.querySelectorAll(".size-5.shrink-0.rounded-full")).toHaveLength(3);
  });

  it("renders the composed chat panel skeleton", () => {
    const { container } = render(<WorkflowSessionSkeleton />);
    // ChatPanelSkeleton renders 4 message bubbles + 1 input bar.
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(5);
  });
});
