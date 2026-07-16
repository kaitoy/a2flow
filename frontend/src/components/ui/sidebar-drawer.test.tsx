import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { SidebarDrawer } from "./sidebar-drawer";

/** Wraps {@link SidebarDrawer} with a real trigger button, matching how it's
 * opened in practice, so focus restoration on close is testable. */
function TriggerHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open drawer
      </button>
      <SidebarDrawer open={open} onClose={() => setOpen(false)} label="Test sidebar">
        <nav>
          <button type="button">drawer item</button>
        </nav>
      </SidebarDrawer>
    </>
  );
}

describe("SidebarDrawer", () => {
  it("renders its children in a labelled dialog when open", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByText("open drawer"));

    const dialog = await screen.findByRole("dialog", { name: "Test sidebar" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("drawer item")).toBeInTheDocument();
  });

  it("moves focus into the drawer when it opens", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open drawer"));

    await waitFor(() => expect(screen.getByText("drawer item")).toHaveFocus());
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open drawer"));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open drawer")).toHaveFocus());
  });

  it("closes and returns focus to the trigger after tapping the scrim", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open drawer"));
    await screen.findByRole("dialog");

    const scrim = document.querySelector('button[aria-hidden="true"]');
    if (!scrim) throw new Error("scrim button not found");
    await user.click(scrim);

    await waitFor(() => expect(screen.getByText("open drawer")).toHaveFocus());
  });
});
