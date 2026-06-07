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
});
