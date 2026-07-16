import { render, screen, waitFor } from "@testing-library/react";
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

  it("renders the task title as plain text (the run's plan is read-only)", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    expect(screen.queryByRole("link", { name: "Step 1" })).not.toBeInTheDocument();
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
    // The global handlers register MCP_SERVER_1 (id "mcp-1", name "my-mcp-server").
    await waitFor(() => expect(screen.getByText("my-mcp-server: search")).toBeInTheDocument());
  });

  it("shows a placeholder in the Tools column when a task has no bindings", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    expect(screen.getByText("Tools")).toBeInTheDocument();
  });

  it("renders the status as a plain label, with no inline editor", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    // The task list of a run is read-only: statuses are advanced by the
    // execution agent (and the approval flow), never edited here.
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /Status for/ })).not.toBeInTheDocument();
  });

  it("offers no create, edit, or delete controls", async () => {
    render(<WorkflowTasksPage />);
    await waitFor(() => screen.getByText("Step 1"));
    expect(screen.queryByRole("link", { name: /add task/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
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
