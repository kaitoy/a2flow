import { http } from "msw";
import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowSessionPage from "./page";

/** The default `/workflow-executions/execution-1/session` handler's payload, for `server.use` overrides. */
const WORKFLOW_EXECUTION_1 = {
  id: "execution-1",
  tenantId: "tenant-1",
  sessionId: "executed-session-id",
  workflowId: "wf-1",
  name: "My Workflow",
  description: null,
  agentSkillId: "skill-1",
  agentSkillName: "My Skill",
  agentSkillRepoUrl: "https://github.com/example/repo",
  agentSkillRepoPath: "",
  skillDir: "/tmp/skill",
  initiatorId: "user",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

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

/** Builds a preloaded auth slice so `AuthProvider` renders its children immediately. */
function authState(roles: string[]): Partial<RootState> {
  return {
    auth: {
      user: { id: "user", roles } as User,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

const AUTH_STATE = authState(["developer"]);

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ workflowExecutionId: "execution-1" });
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

describe("WorkflowSessionPage", () => {
  it("renders a breadcrumb trail ending in Session, with the workflow name linking back to it", async () => {
    render(<WorkflowSessionPage />, { preloadedState: AUTH_STATE });
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByRole("link", { name: "My Workflow" })).toHaveAttribute(
      "href",
      "/admin/workflow-executions/execution-1"
    );
    expect(within(nav).getByText("Session")).toHaveAttribute("aria-current", "page");
  });

  it("keeps the workflow-execution crumb linked even when the parent workflow design has been deleted", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions/:id", () =>
        envelope({ ...WORKFLOW_EXECUTION_1, workflowId: null })
      )
    );
    render(<WorkflowSessionPage />, { preloadedState: AUTH_STATE });
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByRole("link", { name: "My Workflow" })).toHaveAttribute(
      "href",
      "/admin/workflow-executions/execution-1"
    );
  });

  it("shows the access-denied state and no toast when loading the execution is FORBIDDEN", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions/:id", () =>
        envelopeErr(
          "FORBIDDEN",
          "Only the execution initiator or a designated approver can access this workflow execution",
          403
        )
      )
    );
    const beforeCount = store.getState().toast.items.length;

    render(<WorkflowSessionPage />, { preloadedState: AUTH_STATE });

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  it("shows the access-denied state when the chat history load is FORBIDDEN", async () => {
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
      forbidden: true,
    });

    render(<WorkflowSessionPage />, { preloadedState: AUTH_STATE });

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("message-list-mock")).not.toBeInTheDocument());
  });
});
