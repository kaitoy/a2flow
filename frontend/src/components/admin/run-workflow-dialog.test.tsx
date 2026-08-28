import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { RunWorkflowDialog } from "./run-workflow-dialog";

function renderDialog(overrides: Partial<Parameters<typeof RunWorkflowDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <RunWorkflowDialog
      open
      workflowName="my-workflow"
      isDraft
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />
  );
  return { onConfirm, onCancel };
}

describe("RunWorkflowDialog", () => {
  it("confirms with no mocks for a published workflow", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog({ isDraft: false });

    expect(screen.queryByText("Mock tools")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run" }));

    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it("lists the registered mocks for a draft workflow", async () => {
    renderDialog();
    expect(await screen.findByRole("checkbox", { name: /search returns nothing/ })).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /approve then reject/ })).toBeVisible();
  });

  it("labels each mock with the tool it stubs", async () => {
    renderDialog();
    expect(
      await screen.findByRole("checkbox", { name: "search returns nothing — search" })
    ).toBeVisible();
  });

  it("passes the checked mocks to onConfirm", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog();

    await user.click(await screen.findByRole("checkbox", { name: /approve then reject/ }));
    await user.click(screen.getByRole("button", { name: "Run" }));

    expect(onConfirm).toHaveBeenCalledWith(["mock-2"]);
  });

  it("unchecks a mock again", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog();

    const checkbox = await screen.findByRole("checkbox", { name: /approve then reject/ });
    await user.click(checkbox);
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Run" }));

    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it("cancels without confirming", async () => {
    const user = userEvent.setup();
    const { onConfirm, onCancel } = renderDialog();

    await waitFor(() => screen.getByRole("checkbox", { name: /search returns nothing/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
