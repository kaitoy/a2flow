import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowTaskTemplateDetailPage from "./page";

const BASE = "http://localhost:8000";

const TEMPLATE = {
  id: "tmpl-1",
  workflowId: "wf-1",
  title: "Template Step 1",
  description: null,
  position: 0,
  dependsOnIds: [],
  toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

function setup(template: unknown = TEMPLATE) {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1", templateId: "tmpl-1" });
  server.use(
    http.get(`${BASE}/api/v1/workflow-task-templates/:templateId`, () => envelope(template))
  );
}

/** Capture the body of the template PATCH the form submits. */
function capturePatch() {
  const captured: { body?: unknown } = {};
  server.use(
    http.patch(`${BASE}/api/v1/workflow-task-templates/:templateId`, async ({ request }) => {
      captured.body = await request.json();
      return envelope(TEMPLATE);
    })
  );
  return captured;
}

describe("WorkflowTaskTemplateDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the template's title", async () => {
    setup();
    render(<WorkflowTaskTemplateDetailPage />);
    expect(await screen.findByRole("heading", { name: "Template Step 1" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("Template Step 1")).toHaveAttribute("aria-current", "page");
  });

  it("prefills the template's bound MCP tools", async () => {
    setup();
    render(<WorkflowTaskTemplateDetailPage />);

    await waitFor(() => expect(screen.getByDisplayValue("Template Step 1")).toBeInTheDocument());
    expect(await screen.findByRole("checkbox", { name: "my-mcp-server: search" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "local-files: search" })).not.toBeChecked();
  });

  it("submits the tools the operator checks", async () => {
    setup({ ...TEMPLATE, toolBindings: [] });
    const captured = capturePatch();

    render(<WorkflowTaskTemplateDetailPage />);
    await waitFor(() => screen.getByDisplayValue("Template Step 1"));
    await userEvent.click(await screen.findByRole("checkbox", { name: "local-files: search" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(captured.body).toMatchObject({
        title: "Template Step 1",
        toolBindings: [{ mcpServerId: "mcp-2", toolName: "search" }],
      })
    );
  });

  it("submits an empty list when the operator unbinds every tool", async () => {
    setup();
    const captured = capturePatch();

    render(<WorkflowTaskTemplateDetailPage />);
    await waitFor(() => screen.getByDisplayValue("Template Step 1"));
    await userEvent.click(await screen.findByRole("checkbox", { name: "my-mcp-server: search" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(captured.body).toMatchObject({ toolBindings: [] }));
  });

  it("keeps an existing binding editable when its server is unreachable", async () => {
    setup();
    server.use(
      http.get(`${BASE}/api/v1/mcp-servers/:serverId/tools`, () =>
        envelopeErr("MCP_UNREACHABLE", "connection refused", 502)
      )
    );
    const captured = capturePatch();

    render(<WorkflowTaskTemplateDetailPage />);
    await waitFor(() => screen.getByDisplayValue("Template Step 1"));

    // The bound tool is still listed (and checked) even though no server
    // answered, so the operator can remove it.
    const bound = await screen.findByRole("checkbox", { name: "my-mcp-server: search" });
    expect(bound).toBeChecked();

    await userEvent.click(bound);
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(captured.body).toMatchObject({ toolBindings: [] }));
  });
});
