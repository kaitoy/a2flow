import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import PlanningSessionPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const useWorkflowSessionChatMock = vi.fn();

vi.mock("@/hooks/useWorkflowSessionChat", () => ({
  useWorkflowSessionChat: (...args: unknown[]) => useWorkflowSessionChatMock(...args),
}));

vi.mock("@/components/MessageList", () => ({
  MessageList: () => <div data-testid="message-list-mock" />,
}));

vi.mock("@/components/ChatInput", () => ({
  ChatInput: () => <div data-testid="chat-input-mock" />,
}));

/** Preloaded auth slice so AuthProvider renders its children immediately. */
const AUTH_STATE: Partial<RootState> = {
  auth: { user: { id: "user", roles: ["developer"] } as User, status: "authenticated" },
};

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ planningSessionId: "ps-1" });
  useWorkflowSessionChatMock.mockReturnValue({
    messages: [],
    isRunning: false,
    isStreaming: false,
    error: null,
    pendingRenderCalls: [],
    sendMessage: vi.fn(),
    sendA2uiAction: vi.fn(),
    sendApprovalResult: vi.fn(),
    messageSenders: new Map(),
    senderUsers: new Map(),
    locallySentMessageIds: new Set(),
    messageTasks: new Map(),
    tasks: [],
  });
});

describe("PlanningSessionPage", () => {
  it("renders a breadcrumb trail ending in Planning, with the workflow name linking back to it", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByRole("link", { name: "my-workflow" })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1"
    );
    expect(within(nav).getByText("Planning")).toHaveAttribute("aria-current", "page");
  });

  it("drives the chat hook in planning mode with no kickoff prompt", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    await screen.findByRole("link", { name: "my-workflow" });
    expect(useWorkflowSessionChatMock).toHaveBeenCalledWith(
      "ps-1",
      "planning-session-id",
      null,
      "user",
      "planning"
    );
  });

  it("renders the template timeline entries", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    // The global handlers serve WORKFLOW_TASK_TEMPLATE_1 for the workflow.
    await waitFor(() => expect(screen.getByText("Template Step 1")).toBeInTheDocument());
  });

  it("shows a tool-count indicator for a template with bound tools", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id/task-templates", () =>
        envelope([
          {
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
          },
        ])
      )
    );
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    await waitFor(() => expect(screen.getByText("Template Step 1")).toBeInTheDocument());
    expect(screen.getByLabelText("1 bound tool")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("1 bound tool"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("search")).toBeInTheDocument();
    expect(await within(dialog).findByText("my-mcp-server")).toBeInTheDocument();
  });
});
