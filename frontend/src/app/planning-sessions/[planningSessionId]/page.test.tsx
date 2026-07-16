import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { render, screen, waitFor } from "@/test/test-utils";
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
  it("renders the planning header with the workflow name", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    await waitFor(() => expect(screen.getByText(/Planning: my-workflow/)).toBeInTheDocument());
  });

  it("drives the chat hook in planning mode with no kickoff prompt", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    await waitFor(() => screen.getByText(/Planning: my-workflow/));
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

  it("links back to the workflow detail page", async () => {
    render(<PlanningSessionPage />, { preloadedState: AUTH_STATE });
    await waitFor(() => screen.getByText(/Planning: my-workflow/));
    expect(screen.getByRole("link", { name: /open workflow/i })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1"
    );
  });
});
