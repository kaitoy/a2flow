import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApprovalStatusLabel } from "./approval-status";

describe("ApprovalStatusLabel", () => {
  it.each([
    ["pending", "text-on-surface-variant"],
    ["approved", "text-accent"],
    ["rejected", "text-error"],
    ["returned", "text-alert"],
  ] as const)("colours %s with %s", (status, className) => {
    render(<ApprovalStatusLabel status={status} />);
    expect(screen.getByText(status)).toHaveClass(className);
  });

  it("reads a missing status as pending, the state an approval starts in", () => {
    render(<ApprovalStatusLabel />);
    expect(screen.getByText("pending")).toHaveClass("text-on-surface-variant");
  });

  it("reads a null status as pending", () => {
    render(<ApprovalStatusLabel status={null} />);
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
});
