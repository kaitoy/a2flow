import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";
import { Dialog } from "./dialog";

/** Wraps {@link Dialog} with a real trigger so focus restoration is testable. */
function TriggerHarness({ footer }: { footer?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        panelId="test-dialog"
        title="Pick a thing"
        description="Choose carefully."
        footer={footer}
      >
        <button type="button">body button</button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("renders nothing until it is opened", () => {
    render(<TriggerHarness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("names the panel by its title and shows the description", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));

    const dialog = await screen.findByRole("dialog", { name: "Pick a thing" });
    expect(within(dialog).getByText("Choose carefully.")).toBeInTheDocument();
    expect(dialog).toHaveAttribute("id", "test-dialog");
  });

  it("moves focus into the panel on open", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "body button" })).toHaveFocus()
    );
  });

  it("closes and restores focus on Escape", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("closes when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");

    const backdrop = document.querySelector('button[aria-hidden="true"]');
    if (!backdrop) throw new Error("backdrop button not found");
    await user.click(backdrop);

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("renders the footer below the body", async () => {
    const user = userEvent.setup();
    render(
      <TriggerHarness
        footer={
          <Button type="button" variant="ghost">
            Cancel
          </Button>
        }
      />
    );

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});
