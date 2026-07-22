import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TableHeaderMenu } from "./table-header-menu";

describe("TableHeaderMenu", () => {
  it("opens a menu with sort actions and the filter field from the header trigger", async () => {
    const user = userEvent.setup();
    render(
      <TableHeaderMenu
        label="Name"
        sortDirection={null}
        onSortChange={vi.fn()}
        filterValue=""
        onFilterChange={vi.fn()}
      />
    );
    const trigger = screen.getByRole("button", { name: "Name" });
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("button", { name: "Sort ascending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sort descending" })).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("moves focus to the first sort action when it opens", async () => {
    const user = userEvent.setup();
    render(
      <TableHeaderMenu
        label="Name"
        sortDirection={null}
        onSortChange={vi.fn()}
        filterValue=""
        onFilterChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: "Name" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Sort ascending" })).toHaveFocus()
    );
  });

  it("moves focus into the text field for a filter-only column", async () => {
    const user = userEvent.setup();
    render(<TableHeaderMenu label="Name" filterValue="" onFilterChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Name" }));

    await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());
    expect(screen.queryByRole("button", { name: "Sort ascending" })).not.toBeInTheDocument();
  });

  it("moves focus into the select when options are provided", async () => {
    const user = userEvent.setup();
    render(
      <TableHeaderMenu
        label="Status"
        filterValue=""
        onFilterChange={vi.fn()}
        filterOptions={[{ label: "Active", value: "active" }]}
      />
    );

    await user.click(screen.getByRole("button", { name: "Status" }));

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Filter Status" })).toHaveFocus()
    );
  });

  it("emits the clicked sort direction and closes the menu", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    render(<TableHeaderMenu label="Name" sortDirection={null} onSortChange={onSortChange} />);
    const trigger = screen.getByRole("button", { name: "Name" });

    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Sort descending" }));

    expect(onSortChange).toHaveBeenCalledWith("desc");
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });

  it("clears the sort when the active direction is clicked again", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    render(<TableHeaderMenu label="Name" sortDirection="asc" onSortChange={onSortChange} />);

    await user.click(screen.getByRole("button", { name: "Name" }));
    await user.click(await screen.findByRole("button", { name: "Sort ascending" }));

    expect(onSortChange).toHaveBeenCalledWith(null);
  });

  it("marks the active direction with aria-pressed", async () => {
    const user = userEvent.setup();
    render(<TableHeaderMenu label="Name" sortDirection="desc" onSortChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Name" }));

    expect(await screen.findByRole("button", { name: "Sort descending" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("button", { name: "Sort ascending" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
  });

  it("shows the sort direction and filter state on the trigger", () => {
    const { rerender, container } = render(
      <TableHeaderMenu
        label="Name"
        sortDirection={null}
        onSortChange={vi.fn()}
        filterValue=""
        onFilterChange={vi.fn()}
      />
    );
    // Idle: a subtle menu chevron and an invisible (reserved) filter indicator.
    expect(container.querySelector(".lucide-chevron-down")).toBeInTheDocument();
    expect(container.querySelector('[data-filter-indicator="idle"]')).toBeInTheDocument();

    rerender(
      <TableHeaderMenu
        label="Name"
        sortDirection="asc"
        onSortChange={vi.fn()}
        filterValue="abc"
        onFilterChange={vi.fn()}
      />
    );
    expect(container.querySelector(".lucide-arrow-up")).toBeInTheDocument();
    expect(container.querySelector(".lucide-chevron-down")).not.toBeInTheDocument();
    expect(container.querySelector('[data-filter-indicator="active"]')).toBeInTheDocument();
  });

  it("debounces the text filter and keeps the menu open", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(<TableHeaderMenu label="Name" filterValue="" onFilterChange={onFilterChange} />);
    const trigger = screen.getByRole("button", { name: "Name" });

    await user.click(trigger);
    await user.type(await screen.findByRole("textbox"), "abc");
    // Nothing is emitted per keystroke; the value lands once, debounced.
    expect(onFilterChange).not.toHaveBeenCalled();

    await waitFor(() => expect(onFilterChange).toHaveBeenCalledWith("abc"));
    expect(onFilterChange).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("selects a filter option without closing the outer column menu", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    render(
      <TableHeaderMenu
        label="Status"
        filterValue=""
        onFilterChange={onFilterChange}
        filterOptions={[{ label: "Active", value: "active" }]}
      />
    );
    const trigger = screen.getByRole("button", { name: "Status" });

    await user.click(trigger);
    await user.click(await screen.findByRole("combobox", { name: "Filter Status" }));
    await user.click(await screen.findByRole("option", { name: "Active" }));

    expect(onFilterChange).toHaveBeenCalledWith("active");
    // The nested Select listbox closing must not take the outer column menu
    // down with it (see useDialogA11y's nested-popover handling).
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<TableHeaderMenu label="Name" filterValue="" onFilterChange={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Name" });
    await user.click(trigger);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());

    await user.keyboard("{Escape}");

    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("keeps Tab focus within the panel", async () => {
    const user = userEvent.setup();
    render(
      <TableHeaderMenu
        label="Name"
        sortDirection={null}
        onSortChange={vi.fn()}
        filterValue=""
        onFilterChange={vi.fn()}
      />
    );
    await user.click(screen.getByRole("button", { name: "Name" }));
    const first = await screen.findByRole("button", { name: "Sort ascending" });
    await waitFor(() => expect(first).toHaveFocus());

    // Forward past the last focusable (the filter input) wraps to the first.
    await user.tab();
    await user.tab();
    await user.tab();
    expect(first).toHaveFocus();

    // And backward from the first wraps to the last.
    await user.tab({ shift: true });
    expect(screen.getByRole("textbox")).toHaveFocus();
  });
});
