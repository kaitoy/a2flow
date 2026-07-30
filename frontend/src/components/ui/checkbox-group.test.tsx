import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CheckboxGroup, type CheckboxOption } from "./checkbox-group";

const OPTIONS: CheckboxOption[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

describe("CheckboxGroup", () => {
  it("renders a checkbox per option labeled by its label", () => {
    render(<CheckboxGroup options={OPTIONS} value={[]} onChange={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Gamma" })).toBeInTheDocument();
  });

  it("reflects the selected values as checked", () => {
    render(<CheckboxGroup options={OPTIONS} value={["b"]} onChange={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Alpha" })).not.toBeChecked();
  });

  it("adds a value (in option order) when an unchecked box is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<CheckboxGroup options={OPTIONS} value={["c"]} onChange={onChange} />);
    await user.click(screen.getByRole("checkbox", { name: "Alpha" }));
    expect(onChange).toHaveBeenCalledWith(["a", "c"]);
  });

  it("removes a value when a checked box is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<CheckboxGroup options={OPTIONS} value={["a", "b"]} onChange={onChange} />);
    await user.click(screen.getByRole("checkbox", { name: "Alpha" }));
    expect(onChange).toHaveBeenCalledWith(["b"]);
  });

  it("shows the empty message when there are no options", () => {
    render(
      <CheckboxGroup
        options={[]}
        value={[]}
        onChange={vi.fn()}
        emptyMessage="No other tasks available."
      />
    );
    expect(screen.getByText("No other tasks available.")).toBeInTheDocument();
  });

  it("wraps the rows in a glass panel by default", () => {
    const { container } = render(<CheckboxGroup options={OPTIONS} value={[]} onChange={vi.fn()} />);
    expect(container.firstElementChild?.className).toContain("glass-panel");
  });

  it("drops the glass panel when flush", () => {
    const { container } = render(
      <CheckboxGroup flush options={OPTIONS} value={[]} onChange={vi.fn()} />
    );
    expect(container.firstElementChild?.className).not.toContain("glass-panel");
    expect(screen.getByRole("checkbox", { name: "Alpha" })).toBeInTheDocument();
  });

  it("drops the glass panel from the empty message when flush", () => {
    const { container } = render(
      <CheckboxGroup
        flush
        options={[]}
        value={[]}
        onChange={vi.fn()}
        emptyMessage="Nothing here."
      />
    );
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
    expect(container.firstElementChild?.className).not.toContain("glass-panel");
  });
});
