import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Globe, Terminal } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { SegmentedControl } from "./segmented-control";

const OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

const ICON_OPTIONS = [
  { value: "table" as const, label: "Table", icon: Globe },
  { value: "graph" as const, label: "Graph", icon: Terminal },
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

  it("renders an option's icon without adding it to the accessible name", () => {
    render(
      <SegmentedControl
        options={ICON_OPTIONS}
        value="table"
        onChange={() => {}}
        aria-label="View"
      />
    );
    expect(screen.getByRole("tab", { name: "Table" }).querySelector("svg")).not.toBeNull();
  });

  it("keeps the sliding pill out of the accessibility tree", () => {
    const { container } = render(
      <SegmentedControl options={OPTIONS} value="table" onChange={() => {}} aria-label="View" />
    );
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(1);
  });

  it("makes only the selected option a tab stop", () => {
    render(
      <SegmentedControl options={OPTIONS} value="graph" onChange={() => {}} aria-label="View" />
    );
    expect(screen.getByRole("tab", { name: "Graph" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Table" })).toHaveAttribute("tabindex", "-1");
  });

  it("moves the selection with the arrow keys, wrapping at the ends", async () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl options={OPTIONS} value="table" onChange={onChange} aria-label="View" />
    );
    const selected = screen.getByRole("tab", { name: "Table" });
    selected.focus();

    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenLastCalledWith("graph");

    // Still on "table" (the parent owns `value`), so ArrowLeft wraps to the end.
    await userEvent.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("graph");
  });

  it("jumps to the first and last option with Home and End", async () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl options={OPTIONS} value="graph" onChange={onChange} aria-label="View" />
    );
    screen.getByRole("tab", { name: "Graph" }).focus();

    await userEvent.keyboard("{Home}");
    expect(onChange).toHaveBeenLastCalledWith("table");

    await userEvent.keyboard("{End}");
    expect(onChange).toHaveBeenLastCalledWith("graph");
  });
});
