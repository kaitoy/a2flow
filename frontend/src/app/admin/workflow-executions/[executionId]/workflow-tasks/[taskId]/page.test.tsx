import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, within } from "@/test/test-utils";
import WorkflowTaskDetailPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ executionId: "execution-1", taskId: "task-1" });
});

describe("WorkflowTaskDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the task's title", async () => {
    render(<WorkflowTaskDetailPage />);
    expect(await screen.findByRole("heading", { name: "Step 1" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("Step 1")).toHaveAttribute("aria-current", "page");
  });

  it("adds breadcrumb crumbs for the workflow execution and the task list", async () => {
    render(<WorkflowTaskDetailPage />);
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(await within(nav).findByRole("link", { name: "My Workflow" })).toHaveAttribute(
      "href",
      "/admin/workflow-executions/execution-1"
    );
    expect(within(nav).getByRole("link", { name: "Workflow Tasks" })).toHaveAttribute(
      "href",
      "/admin/workflow-executions/execution-1/workflow-tasks"
    );
  });

  it("shows the task's status", async () => {
    render(<WorkflowTaskDetailPage />);
    expect(await screen.findByText("pending")).toBeInTheDocument();
  });

  it("shows the status in its own status card", async () => {
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    const card = screen.getByRole("region", { name: "Workflow task status" });
    expect(within(card).getByText("pending")).toBeInTheDocument();
  });

  it("resolves a dependency id to its title as a chip", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-2",
          workflowExecutionId: "execution-1",
          title: "Step 2",
          description: null,
          status: "pending",
          dependsOnIds: ["task-1"],
          toolBindings: [],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 2" });
    // "Step 1" is WORKFLOW_TASK_1's title, resolved from the sibling task list.
    expect(await screen.findByText("Step 1")).toBeInTheDocument();
  });

  it("resolves a tool binding's server id to its name as a chip", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-1",
          workflowExecutionId: "execution-1",
          title: "Step 1",
          description: null,
          status: "pending",
          dependsOnIds: [],
          toolBindings: [{ mcpServerId: "mcp-1", toolName: "search" }],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    // "my-mcp-server" is MCP_SERVER_1's name in the default MSW fixtures.
    expect(await screen.findByText("my-mcp-server: search")).toBeInTheDocument();
  });

  it("shows the error kind and message for a failed task", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelope({
          id: "task-1",
          workflowExecutionId: "execution-1",
          title: "Step 1",
          description: null,
          status: "failed",
          errorKind: "timeout",
          errorMessage: "Gave up after 30s",
          dependsOnIds: [],
          toolBindings: [],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    expect(await screen.findByText("timeout")).toBeInTheDocument();
    expect(screen.getByText("Gave up after 30s")).toBeInTheDocument();
  });

  it("offers no delete or edit controls", async () => {
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });

  it("navigates to the task list from the header action", async () => {
    const user = userEvent.setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    await user.click(screen.getByRole("button", { name: "View all tasks" }));
    expect(pushMock).toHaveBeenCalledWith("/admin/workflow-executions/execution-1/workflow-tasks");
  });

  it("cancels back to the task list", async () => {
    const user = userEvent.setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    render(<WorkflowTaskDetailPage />);
    await screen.findByRole("heading", { name: "Step 1" });
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    expect(pushMock).toHaveBeenCalledWith("/admin/workflow-executions/execution-1/workflow-tasks");
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-tasks/:taskId", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    render(<WorkflowTaskDetailPage />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
