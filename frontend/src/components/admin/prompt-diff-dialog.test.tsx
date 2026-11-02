import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { PromptDiffDialog } from "./prompt-diff-dialog";

/** Wraps {@link PromptDiffDialog} with a real trigger button, matching how
 * it's opened in practice, so focus restoration on close is testable. */
function TriggerHarness({
  generated,
  prompt,
  loading,
}: {
  generated: string;
  prompt: string;
  loading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <PromptDiffDialog
        open={open}
        generated={generated}
        prompt={prompt}
        onClose={() => setOpen(false)}
        loading={loading}
      />
    </>
  );
}

/** Opens the harness dialog and returns its panel. */
async function openDialog(generated: string, prompt: string, loading?: boolean) {
  const user = userEvent.setup();
  render(<TriggerHarness generated={generated} prompt={prompt} loading={loading} />);
  await user.click(screen.getByText("open dialog"));
  return { user, dialog: await screen.findByRole("dialog") };
}

describe("PromptDiffDialog", () => {
  it("renders nothing while closed", () => {
    render(<TriggerHarness generated="Runs monthly." prompt="Runs weekly." />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("strikes out words only in the generated prompt and highlights added ones", async () => {
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

  it("explains the fallback instead of diffing when the prompt is empty", async () => {
    const { dialog } = await openDialog("Runs every Monday.", "   ");

    expect(
      within(dialog).getByText("Prompt is empty, so the generated prompt is used as is.")
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
