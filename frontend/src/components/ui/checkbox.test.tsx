import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "./checkbox";

describe("Checkbox", () => {
  it("renders with its label as the accessible name", () => {
    render(<Checkbox label="Enabled" />);
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeInTheDocument();
  });

  it("reflects the checked prop", () => {
    render(<Checkbox label="Enabled" checked readOnly />);
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeChecked();
  });

  it("fires onChange when toggled", async () => {
    const onChange = vi.fn();
    render(<Checkbox label="Enabled" onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Enabled" }));
    expect(onChange).toHaveBeenCalledOnce();
  });

  it("can be disabled", () => {
    render(<Checkbox label="Enabled" disabled />);
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeDisabled();
  });

  it("keeps the label as the accessible name while hiding it visually", () => {
    render(<Checkbox label="Developers" labelHidden />);
    const box = screen.getByRole("checkbox", { name: "Developers" });
    expect(box).toBeInTheDocument();
    expect(screen.getByText("Developers")).toHaveClass("sr-only");
  });

  it("drops the row padding and hover chrome when the label is hidden", () => {
    render(<Checkbox label="Developers" labelHidden />);
    const wrapper = screen.getByRole("checkbox", { name: "Developers" }).closest("label");
    expect(wrapper).toHaveClass("inline-flex");
    expect(wrapper).not.toHaveClass("px-3");
  });

  it("keeps the row padding and hover chrome by default", () => {
    render(<Checkbox label="Developers" />);
    const wrapper = screen.getByRole("checkbox", { name: "Developers" }).closest("label");
    expect(wrapper).toHaveClass("px-3");
  });
});
