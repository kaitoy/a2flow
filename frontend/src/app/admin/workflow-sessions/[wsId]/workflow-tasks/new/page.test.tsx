import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewWorkflowTaskPage from "./page";

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ wsId: "ws-1" }),
  useRouter: () => ({ push: pushMock }),
}));

describe("NewWorkflowTaskPage", () => {
  it("renders the form fields", () => {
    render(<NewWorkflowTaskPage />);
    expect(screen.getByLabelText(/Title/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Status/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Position/)).toBeInTheDocument();
  });

  it("submits to POST /workflow-tasks with the URL session id", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: unknown = null;
    server.use(
      http.post("http://localhost:8000/api/v1/workflow-tasks", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(
          {
            id: "new-task-id",
            workflowSessionId: "ws-1",
            title: "Step 1",
            description: null,
            status: "pending",
            position: 0,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          201
        );
      })
    );

    render(<NewWorkflowTaskPage />);
    await user.type(screen.getByLabelText(/Title/), "Outline doc");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/admin/workflow-sessions/ws-1/workflow-tasks")
    );
    expect(receivedBody).toMatchObject({
      workflowSessionId: "ws-1",
      title: "Outline doc",
      status: "pending",
      position: 0,
    });
  });

  it("renders a dependency picker listing the session's other tasks", async () => {
    render(<NewWorkflowTaskPage />);
    expect(screen.getByText("Depends on")).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Step 1" })).toBeInTheDocument();
  });

  it("includes selected dependencies in the POST body", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> = {};
    server.use(
      http.post("http://localhost:8000/api/v1/workflow-tasks", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope(
          {
            id: "new-task-id",
            workflowSessionId: "ws-1",
            title: "Step 2",
            description: null,
            status: "pending",
            position: 0,
            dependsOnIds: ["task-1"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          201
        );
      })
    );

    render(<NewWorkflowTaskPage />);
    await user.type(screen.getByLabelText(/Title/), "Step 2");
    await user.click(await screen.findByRole("checkbox", { name: "Step 1" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(receivedBody.dependsOnIds).toEqual(["task-1"]);
  });

  it("renders an MCP tool picker listing tools from registered servers", async () => {
    render(<NewWorkflowTaskPage />);
    expect(screen.getByText("MCP Tools")).toBeInTheDocument();
    // The global handlers register MCP_SERVER_1 advertising the "search" tool.
    expect(
      await screen.findByRole("checkbox", { name: "my-mcp-server: search" })
    ).toBeInTheDocument();
  });

  it("includes selected tool bindings in the POST body", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> = {};
    server.use(
      http.post("http://localhost:8000/api/v1/workflow-tasks", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope(
          {
            id: "new-task-id",
            workflowSessionId: "ws-1",
            title: "Step 2",
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
          201
        );
      })
    );

    render(<NewWorkflowTaskPage />);
    await user.type(screen.getByLabelText(/Title/), "Step 2");
    await user.click(await screen.findByRole("checkbox", { name: "my-mcp-server: search" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(receivedBody.toolBindings).toEqual([{ mcpServerId: "mcp-1", toolName: "search" }]);
  });

  it("shows an error banner when the create call fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/workflow-tasks",
        () => new HttpResponse(null, { status: 500 })
      )
    );

    render(<NewWorkflowTaskPage />);
    await user.type(screen.getByLabelText(/Title/), "Outline doc");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("blocks submission when title is empty", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    render(<NewWorkflowTaskPage />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/at least 1 character/i)).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
