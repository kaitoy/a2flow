import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ColumnPicker } from "./column-picker";

const OPTIONS = [
  { value: "Type", label: "Type" },
  { value: "Reference", label: "Reference" },
];

/** Render the picker with sensible defaults, returning the mocked callbacks. */
function setup(props: Partial<React.ComponentProps<typeof ColumnPicker>> = {}) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  render(
    <ColumnPicker
      options={OPTIONS}
      value={["Type"]}
      onChange={onChange}
      onReset={onReset}
      customized={false}
      {...props}
    />
  );
  return { onChange, onReset };
}

describe("ColumnPicker", () => {
  it("opens a checkbox panel from the Columns trigger", async () => {
    const user = userEvent.setup();
    setup();
    const trigger = screen.getByRole("button", { name: "Columns" });
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const panel = await screen.findByRole("dialog", { name: "Column visibility" });
    expect(panel).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Type" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Reference" })).not.toBeChecked();
  });

  it("emits the next selection when a column is toggled on", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Reference" }));

    expect(onChange).toHaveBeenCalledWith(["Type", "Reference"]);
  });

  it("emits the next selection when a column is toggled off", async () => {
    const user = userEvent.setup();
    const { onChange } = setup();

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Type" }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("stays open after a toggle so several columns can be adjusted at once", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Reference" }));

    expect(screen.getByRole("dialog", { name: "Column visibility" })).toBeInTheDocument();
  });

  it("disables the reset action until the selection differs from the defaults", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByRole("button", { name: "Columns" }));

    expect(await screen.findByRole("button", { name: /reset to default/i })).toBeDisabled();
  });

  it("calls onReset from the reset action", async () => {
    const user = userEvent.setup();
    const { onReset } = setup({ customized: true });

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("button", { name: /reset to default/i }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape and restores focus to the trigger", async () => {
    const user = userEvent.setup();
    setup();
    const trigger = screen.getByRole("button", { name: "Columns" });

    await user.click(trigger);
    await screen.findByRole("dialog", { name: "Column visibility" });
    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Column visibility" })).not.toBeInTheDocument()
    );
    expect(trigger).toHaveFocus();
  });

  it("closes on an outside click", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await screen.findByRole("dialog", { name: "Column visibility" });
    await user.click(document.body);

    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Column visibility" })).not.toBeInTheDocument()
    );
  });

  it("explains itself when the table offers no toggleable columns", async () => {
    const user = userEvent.setup();
    setup({ options: [], value: [] });

    await user.click(screen.getByRole("button", { name: "Columns" }));

    expect(await screen.findByText("Every column is always shown.")).toBeInTheDocument();
  });
});
