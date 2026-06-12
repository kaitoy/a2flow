import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import EditWorkflowTaskPage from "./page";

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ wsId: "ws-1", taskId: "task-1" }),
  useRouter: () => ({ push: pushMock }),
}));

describe("EditWorkflowTaskPage", () => {
  it("prefills the form with the loaded task", async () => {
    render(<EditWorkflowTaskPage />);
    const titleInput = await screen.findByLabelText<HTMLInputElement>(/Title/);
    expect(titleInput.value).toBe("Step 1");
  });

  it("submits PATCH and navigates back to the tasks list", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: unknown = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/workflow-tasks/:taskId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Renamed",
          description: null,
          status: "in_progress",
          position: 2,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowTaskPage />);
    const title = await screen.findByLabelText<HTMLInputElement>(/Title/);
    await user.clear(title);
    await user.type(title, "Renamed");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/admin/workflow-sessions/ws-1/workflow-tasks")
    );
    expect(receivedBody).toMatchObject({ title: "Renamed" });
  });

  it("does not include workflowSessionId in PATCH body (parent is immutable)", async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> = {};
    server.use(
      http.patch("http://localhost:8000/api/v1/workflow-tasks/:taskId", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowTaskPage />);
    await screen.findByLabelText(/Title/);
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(Object.keys(receivedBody).length).toBeGreaterThan(0));
    expect(receivedBody).not.toHaveProperty("workflowSessionId");
  });

  it("prefills selected dependencies, excludes self, and PATCHes dependsOnIds", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> = {};
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          dependsOnIds: ["task-2"],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      ),
      http.get("http://localhost:8000/api/v1/workflow-sessions/:wsId/workflow-tasks", () =>
        envelope([
          {
            id: "task-1",
            workflowSessionId: "ws-1",
            title: "Step 1",
            description: null,
            status: "pending",
            position: 0,
            dependsOnIds: ["task-2"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          {
            id: "task-2",
            workflowSessionId: "ws-1",
            title: "Step 2",
            description: null,
            status: "pending",
            position: 1,
            dependsOnIds: [],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      ),
      http.patch("http://localhost:8000/api/v1/workflow-tasks/:taskId", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          dependsOnIds: ["task-2"],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowTaskPage />);
    // The task depends on task-2, so its checkbox is pre-checked.
    expect(await screen.findByRole("checkbox", { name: "Step 2" })).toBeChecked();
    // The task itself (Step 1) must not be a candidate dependency.
    expect(screen.queryByRole("checkbox", { name: "Step 1" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(receivedBody.dependsOnIds).toEqual(["task-2"]);
  });

  it("prefills bound MCP tools and PATCHes toolBindings", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> = {};
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          dependsOnIds: [],
          toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      ),
      http.patch("http://localhost:8000/api/v1/workflow-tasks/:taskId", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          dependsOnIds: [],
          toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowTaskPage />);
    // The task binds MCP_SERVER_1's "search" tool, so its checkbox is pre-checked.
    expect(await screen.findByRole("checkbox", { name: "My MCP Server: search" })).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(receivedBody.toolBindings).toEqual([{ mcpServerId: "mcp-1", toolName: "search" }]);
  });

  it("keeps a bound tool selectable when its server is unreachable", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: "pending",
          position: 0,
          dependsOnIds: [],
          toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      ),
      http.get(
        "http://localhost:8000/api/v1/mcp-servers/:serverId/tools",
        () => new HttpResponse(null, { status: 502 })
      )
    );

    render(<EditWorkflowTaskPage />);
    // The catalog fetch fails, but the existing binding is merged in (labeled
    // with the registered server name) so it stays visible and deselectable.
    expect(await screen.findByRole("checkbox", { name: "My MCP Server: search" })).toBeChecked();
  });

  it("opens the confirm dialog and calls DELETE", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-tasks/:taskId", deleteSpy));

    render(<EditWorkflowTaskPage />);
    await screen.findByLabelText(/Title/);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));

    expect(deleteSpy).toHaveBeenCalled();
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/admin/workflow-sessions/ws-1/workflow-tasks")
    );
  });

  it("shows an error banner when the update fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch(
        "http://localhost:8000/api/v1/workflow-tasks/:taskId",
        () => new HttpResponse(null, { status: 500 })
      )
    );

    render(<EditWorkflowTaskPage />);
    await screen.findByLabelText(/Title/);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });
});
