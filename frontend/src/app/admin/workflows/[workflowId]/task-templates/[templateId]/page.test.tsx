import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
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
  dependsOnIds: [],
  toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user",
  updatedBy: "",
};

function setup(template: unknown = TEMPLATE) {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1", templateId: "tmpl-1" });
  server.use(
    http.get(`${BASE}/api/v1/workflow-task-templates/:templateId`, () => envelope(template)),
    http.get(`${BASE}/api/v1/workflows/:id`, () =>
      envelope({
        id: "wf-1",
        tenantId: "tenant-1",
        name: "My Workflow",
        description: null,
        agentSkillId: "skill-1",
        sessionId: "design-session-id",
        agentSkillCommitSha: "a".repeat(40),
        status: "draft",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "user",
        updatedBy: "",
      })
    )
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

  it("adds a breadcrumb crumb linking back to the parent workflow", async () => {
    setup();
    render(<WorkflowTaskTemplateDetailPage />);
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    const link = await within(nav).findByRole("link", { name: "My Workflow" });
    expect(link).toHaveAttribute("href", "/admin/workflows/wf-1");
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

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1", templateId: "tmpl-1" });
    server.use(
      http.get(`${BASE}/api/v1/workflow-task-templates/:templateId`, () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    render(<WorkflowTaskTemplateDetailPage />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
