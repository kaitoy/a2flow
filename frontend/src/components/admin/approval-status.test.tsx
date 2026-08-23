import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApprovalStatusLabel } from "./approval-status";

/** The dot itself carries no text, so tests reach for it by its shape classes. */
function dot(container: HTMLElement) {
  return container.querySelector(".size-2.rounded-full");
}

describe("ApprovalStatusLabel", () => {
  it.each([
    ["pending", "bg-on-surface-variant"],
    ["approved", "bg-success/80"],
    ["rejected", "bg-error"],
    ["returned", "bg-accent"],
  ] as const)("marks %s with a %s dot", (status, dotClass) => {
    const { container } = render(<ApprovalStatusLabel status={status} />);
    expect(dot(container)?.className).toContain(dotClass);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it("leaves the status name achromatic, so only the dot carries the colour", () => {
    render(<ApprovalStatusLabel status="rejected" />);
    expect(screen.getByText("rejected").className).toBe("capitalize");
  });

  it("reads a missing status as pending, the state an approval starts in", () => {
    const { container } = render(<ApprovalStatusLabel />);
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(dot(container)?.className).toContain("bg-on-surface-variant");
  });

  it("reads a null status as pending", () => {
    render(<ApprovalStatusLabel status={null} />);
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
});
