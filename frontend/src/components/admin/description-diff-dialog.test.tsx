import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { DescriptionDiffDialog } from "./description-diff-dialog";

/** Wraps {@link DescriptionDiffDialog} with a real trigger button, matching how
 * it's opened in practice, so focus restoration on close is testable. */
function TriggerHarness({
  generated,
  description,
  loading,
}: {
  generated: string;
  description: string;
  loading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <DescriptionDiffDialog
        open={open}
        generated={generated}
        description={description}
        onClose={() => setOpen(false)}
        loading={loading}
      />
    </>
  );
}

/** Opens the harness dialog and returns its panel. */
async function openDialog(generated: string, description: string, loading?: boolean) {
  const user = userEvent.setup();
  render(<TriggerHarness generated={generated} description={description} loading={loading} />);
  await user.click(screen.getByText("open dialog"));
  return { user, dialog: await screen.findByRole("dialog") };
}

describe("DescriptionDiffDialog", () => {
  it("renders nothing while closed", () => {
    render(<TriggerHarness generated="Runs monthly." description="Runs weekly." />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("strikes out words only in the generated description and highlights added ones", async () => {
    const { dialog } = await openDialog(
      "Collects the monthly sales report.",
      "Collects the weekly sales report."
    );

    const removed = Array.from(dialog.querySelectorAll("del")).map((el) => el.textContent?.trim());
    const added = Array.from(dialog.querySelectorAll("ins")).map((el) => el.textContent?.trim());

    expect(removed).toEqual(["monthly"]);
    expect(added).toEqual(["weekly"]);
    // Unchanged text stays in the body without either marker.
    expect(dialog).toHaveTextContent("Collects the");
    expect(dialog).toHaveTextContent("sales report.");
  });

  it("reports no differences when both texts match", async () => {
    const { dialog } = await openDialog("Runs every Monday.", "Runs every Monday.");

    expect(within(dialog).getByText(/No differences/)).toBeInTheDocument();
    expect(dialog.querySelectorAll("del")).toHaveLength(0);
    expect(dialog.querySelectorAll("ins")).toHaveLength(0);
  });

  it("explains the fallback instead of diffing when the description is empty", async () => {
    const { dialog } = await openDialog("Runs every Monday.", "   ");

    expect(
      within(dialog).getByText("Description is empty, so the generated description is used as is.")
    ).toBeInTheDocument();
    expect(dialog.querySelectorAll("del")).toHaveLength(0);
  });

  it("shows a loading skeleton and the live edge instead of the diff while generating", async () => {
    const { dialog } = await openDialog("Runs monthly.", "Runs weekly.", true);

    expect(dialog.className).toContain("live-edge");
    expect(within(dialog).getByRole("status", { name: "Generating" })).toBeInTheDocument();
    expect(dialog.querySelectorAll("del")).toHaveLength(0);
    expect(dialog.querySelectorAll("ins")).toHaveLength(0);
    expect(within(dialog).queryByText(/No differences/)).not.toBeInTheDocument();
  });

  it("does not carry the live edge once loading is done", async () => {
    const { dialog } = await openDialog("Runs monthly.", "Runs weekly.", false);

    expect(dialog.className).not.toContain("live-edge");
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const { user } = await openDialog("Runs monthly.", "Runs weekly.");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("closes and returns focus to the trigger via the Close button", async () => {
    const { user, dialog } = await openDialog("Runs monthly.", "Runs weekly.");

    await user.click(within(dialog).getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });
});
