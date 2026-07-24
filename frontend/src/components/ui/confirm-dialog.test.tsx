import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./confirm-dialog";

/** Wraps {@link ConfirmDialog} with a real trigger button, matching how it's
 * opened in practice, so focus restoration on close is testable. */
function TriggerHarness({
  onConfirm,
  confirmLabel,
  confirmVariant,
}: {
  onConfirm: () => void;
  confirmLabel?: string;
  confirmVariant?: "danger" | "primary" | "secondary";
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <ConfirmDialog
        open={open}
        title="Delete item?"
        description="This cannot be undone."
        confirmLabel={confirmLabel}
        confirmVariant={confirmVariant}
        onConfirm={() => {
          setOpen(false);
          onConfirm();
        }}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

describe("ConfirmDialog", () => {
  it("moves focus into the dialog when it opens", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness onConfirm={vi.fn()} />);

    await user.click(screen.getByText("open dialog"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus()
    );
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness onConfirm={vi.fn()} />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("closes and returns focus to the trigger after clicking the backdrop", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness onConfirm={vi.fn()} />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");

    const backdrop = document.querySelector('button[aria-hidden="true"]');
    if (!backdrop) throw new Error("backdrop button not found");
    await user.click(backdrop);

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("wraps Tab from Delete back to Cancel", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness onConfirm={vi.fn()} />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus()
    );

    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Delete" })).toHaveFocus();
    await user.tab();

    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("confirms via the Delete button", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<TriggerHarness onConfirm={onConfirm} />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(onConfirm).toHaveBeenCalled();
  });

  it("renders a custom confirmLabel instead of the default Delete", async () => {
    const user = userEvent.setup();
    render(
      <TriggerHarness onConfirm={vi.fn()} confirmLabel="Impersonate" confirmVariant="primary" />
    );

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Impersonate" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });
});
