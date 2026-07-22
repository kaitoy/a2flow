import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Select } from "./select";

const OPTIONS = [
  { value: "a", label: "Acme Corp" },
  { value: "b", label: "Globex" },
  { value: "c", label: "Initech" },
];

describe("Select", () => {
  it("shows the selected option's label on the trigger", () => {
    render(<Select options={OPTIONS} value="b" onChange={vi.fn()} aria-label="Tenant" />);
    expect(screen.getByRole("combobox", { name: "Tenant" })).toHaveTextContent("Globex");
  });

  it("opens the listbox and lists every option on click", async () => {
    const user = userEvent.setup();
    render(<Select options={OPTIONS} value="a" onChange={vi.fn()} aria-label="Tenant" />);

    await user.click(screen.getByRole("combobox", { name: "Tenant" }));

    expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Initech" })).toBeInTheDocument();
  });

  it("marks the currently selected option as aria-selected", async () => {
    const user = userEvent.setup();
    render(<Select options={OPTIONS} value="b" onChange={vi.fn()} aria-label="Tenant" />);

    await user.click(screen.getByRole("combobox", { name: "Tenant" }));

    expect(screen.getByRole("option", { name: "Globex" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: "Acme Corp" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("calls onChange with the clicked option's value and closes the listbox", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Select options={OPTIONS} value="a" onChange={onChange} aria-label="Tenant" />);
    const trigger = screen.getByRole("combobox", { name: "Tenant" });

    await user.click(trigger);
    await user.click(screen.getByRole("option", { name: "Globex" }));

    expect(onChange).toHaveBeenCalledWith("b");
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });

  it("moves the highlight with arrow keys and commits with Enter", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Select options={OPTIONS} value="a" onChange={onChange} aria-label="Tenant" />);
    const trigger = screen.getByRole("combobox", { name: "Tenant" });

    await user.click(trigger);
    await waitFor(() => expect(screen.getByRole("listbox")).toHaveFocus());
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("closes on Escape and restores focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<Select options={OPTIONS} value="a" onChange={vi.fn()} aria-label="Tenant" />);
    const trigger = screen.getByRole("combobox", { name: "Tenant" });

    await user.click(trigger);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.keyboard("{Escape}");

    await waitFor(() => expect(trigger).toHaveFocus());
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("does not open when disabled", async () => {
    const user = userEvent.setup();
    render(<Select options={OPTIONS} value="a" onChange={vi.fn()} aria-label="Tenant" disabled />);
    const trigger = screen.getByRole("combobox", { name: "Tenant" });

    expect(trigger).toBeDisabled();
    await user.click(trigger);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
