import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SegmentedControl } from "./segmented-control";

const OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

describe("SegmentedControl", () => {
  it("renders all options as tabs", () => {
    render(
      <SegmentedControl options={OPTIONS} value="table" onChange={() => {}} aria-label="View" />
    );
    expect(screen.getByRole("tab", { name: "Table" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Graph" })).toBeInTheDocument();
  });

  it("marks the selected option with aria-selected", () => {
    render(
      <SegmentedControl options={OPTIONS} value="graph" onChange={() => {}} aria-label="View" />
    );
    expect(screen.getByRole("tab", { name: "Graph" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Table" })).toHaveAttribute("aria-selected", "false");
  });

  it("calls onChange with the clicked value", async () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl options={OPTIONS} value="table" onChange={onChange} aria-label="View" />
    );
    await userEvent.click(screen.getByRole("tab", { name: "Graph" }));
    expect(onChange).toHaveBeenCalledWith("graph");
  });
});
