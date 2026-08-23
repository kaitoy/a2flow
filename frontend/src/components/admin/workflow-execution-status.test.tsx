import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WorkflowExecutionStatusLabel } from "./workflow-execution-status";

/** The dot itself carries no text, so tests reach for it by its shape classes. */
function dot(container: HTMLElement) {
  return container.querySelector(".size-2.rounded-full");
}

describe("WorkflowExecutionStatusLabel", () => {
  it.each([
    ["running", "bg-accent"],
    ["completed", "bg-success/80"],
    ["failed", "bg-error"],
  ] as const)("marks %s with a %s dot", (status, dotClass) => {
    const { container } = render(<WorkflowExecutionStatusLabel status={status} />);
    expect(dot(container)?.className).toContain(dotClass);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it("leaves the status name achromatic, so only the dot carries the colour", () => {
    render(<WorkflowExecutionStatusLabel status="failed" />);
    expect(screen.getByText("failed").className).toBe("capitalize");
  });

  it("reads a missing status as running, the state an execution starts in", () => {
    const { container } = render(<WorkflowExecutionStatusLabel />);
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(dot(container)?.className).toContain("bg-accent");
  });

  it("reads a null status as running", () => {
    render(<WorkflowExecutionStatusLabel status={null} />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });
});
