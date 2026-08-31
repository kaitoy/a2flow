import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { MCP_TOOL_MOCK_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { RunWorkflowDialog } from "./run-workflow-dialog";

const BASE = "http://localhost:8000";

/** Serve one task template for `wf-1` with the given tool bindings. */
function templatesWithBindings(toolBindings: Array<{ mcpServerId: string; toolName: string }>) {
  server.use(
    http.get(`${BASE}/api/v1/workflows/:id/task-templates`, () =>
      envelope([
        {
          id: "tmpl-1",
          workflowId: "wf-1",
          title: "Template Step 1",
          description: null,
          dependsOnIds: [],
          toolBindings,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        },
      ])
    )
  );
}

function renderDialog(overrides: Partial<Parameters<typeof RunWorkflowDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <RunWorkflowDialog
      open
      workflowId="wf-1"
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

  it("hides a mock whose MCP tool no task in the workflow binds", async () => {
    templatesWithBindings([]);
    renderDialog();

    // The built-in mock is always reachable, so it anchors the wait.
    expect(await screen.findByRole("checkbox", { name: /approve then reject/ })).toBeVisible();
    expect(
      screen.queryByRole("checkbox", { name: /search returns nothing/ })
    ).not.toBeInTheDocument();
  });

  it("keeps a mock whose tool a task binds", async () => {
    templatesWithBindings([{ mcpServerId: "mcp-1", toolName: "search" }]);
    renderDialog();

    expect(await screen.findByRole("checkbox", { name: /search returns nothing/ })).toBeVisible();
  });

  it("explains when no registered mock applies to the workflow", async () => {
    server.use(http.get(`${BASE}/api/v1/mcp-tool-mocks`, () => envelope([MCP_TOOL_MOCK_1])));
    templatesWithBindings([]);
    const { onConfirm } = renderDialog();
    const user = userEvent.setup();

    expect(
      await screen.findByText("No registered tool mock targets a tool this workflow uses.")
    ).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    // An unstubbed run is still possible from this state.
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it("falls back to every mock when the task templates cannot be loaded", async () => {
    server.use(http.get(`${BASE}/api/v1/workflows/:id/task-templates`, () => envelope(null, 500)));
    renderDialog();

    expect(await screen.findByRole("checkbox", { name: /search returns nothing/ })).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /approve then reject/ })).toBeVisible();
  });
});
