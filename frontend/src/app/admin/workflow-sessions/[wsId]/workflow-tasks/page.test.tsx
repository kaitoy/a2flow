import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import WorkflowTasksPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ wsId: "ws-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

describe("WorkflowTasksPage", () => {
  it("renders task row after load", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => expect(screen.getByText("Step 1")).toBeInTheDocument());
  });

  it("renders Edit link to the task detail route", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    const link = screen.getByRole("link", { name: "Edit" });
    expect(link).toHaveAttribute("href", "/admin/workflow-sessions/ws-1/workflow-tasks/task-1");
  });

  it("renders a Depends on column resolving dependency ids to titles", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-sessions/:wsId/workflow-tasks", () =>
        envelope([
          {
            id: "task-1",
            workflowSessionId: "ws-1",
            title: "Step 1",
            description: null,
            status: "pending",
            position: 0,
            dependsOnIds: [],
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
            dependsOnIds: ["task-1"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );

    render(<WorkflowTasksPage />);
    expect(await screen.findByText("Depends on")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Step 2")).toBeInTheDocument());
    // "Step 1" appears twice: once as task-1's own title, once as task-2's
    // resolved dependency chip.
    expect(screen.getAllByText("Step 1")).toHaveLength(2);
  });

  it("renders a Tools column resolving server ids to names", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-sessions/:wsId/workflow-tasks", () =>
        envelope([
          {
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
          },
        ])
      )
    );

    render(<WorkflowTasksPage />);
    expect(await screen.findByText("Tools")).toBeInTheDocument();
    // The global handlers register MCP_SERVER_1 (id "mcp-1", name "My MCP Server").
    await waitFor(() => expect(screen.getByText("My MCP Server: search")).toBeInTheDocument());
  });

  it("shows a placeholder in the Tools column when a task has no bindings", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    expect(screen.getByText("Tools")).toBeInTheDocument();
  });

  it("calls PATCH when the inline status select changes", async () => {
    const user = userEvent.setup();
    const patchSpy = vi.fn(({ request }: { request: Request }) =>
      request.json().then((body) =>
        envelope({
          id: "task-1",
          workflowSessionId: "ws-1",
          title: "Step 1",
          description: null,
          status: (body as { status: string }).status,
          position: 0,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    server.use(http.patch("http://localhost:8000/api/v1/workflow-tasks/:taskId", patchSpy));

    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));

    const select = screen.getByLabelText(/Status for Step 1/);
    await user.selectOptions(select, "completed");

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-tasks/:taskId", deleteSpy));

    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("shows an error banner when load fails", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/workflow-sessions/:wsId/workflow-tasks",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<WorkflowTasksPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });
});
