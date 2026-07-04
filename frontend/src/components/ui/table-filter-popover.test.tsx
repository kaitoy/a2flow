import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TableFilterPopover } from "./table-filter-popover";

describe("TableFilterPopover", () => {
  it("moves focus into the text field when it opens", async () => {
    const user = userEvent.setup();
    render(<TableFilterPopover label="Name" value="" onChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Filter Name" }));

    await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());
  });

  it("moves focus into the select when options are provided", async () => {
    const user = userEvent.setup();
    render(
      <TableFilterPopover
        label="Status"
        value=""
        onChange={vi.fn()}
        options={[{ label: "Active", value: "active" }]}
      />
    );

    await user.click(screen.getByRole("button", { name: "Filter Status" }));

    await waitFor(() => expect(screen.getByRole("combobox")).toHaveFocus());
  });

  it("closes and returns focus to the funnel button on Escape", async () => {
    const user = userEvent.setup();
    render(<TableFilterPopover label="Name" value="" onChange={vi.fn()} />);
    const button = screen.getByRole("button", { name: "Filter Name" });
    await user.click(button);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());

    await user.keyboard("{Escape}");

    await waitFor(() => expect(button).toHaveFocus());
  });

  it("keeps focus on the single field when pressing Tab", async () => {
    const user = userEvent.setup();
    render(<TableFilterPopover label="Name" value="" onChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Filter Name" }));
    const input = await screen.findByRole("textbox");
    await waitFor(() => expect(input).toHaveFocus());

    await user.tab();

    expect(input).toHaveFocus();
  });
});
