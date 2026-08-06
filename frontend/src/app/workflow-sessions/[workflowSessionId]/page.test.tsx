import { http } from "msw";
import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, within } from "@/test/test-utils";
import WorkflowSessionPage from "./page";

/** The default `/workflow-sessions/ws-1` handler's payload, for `server.use` overrides. */
const WORKFLOW_SESSION_1 = {
  id: "ws-1",
  tenantId: "tenant-1",
  sessionId: "executed-session-id",
  workflowId: "wf-1",
  workflowName: "My Workflow",
  workflowDescription: null,
  agentSkillId: "skill-1",
  agentSkillName: "My Skill",
  agentSkillRepoUrl: "https://github.com/example/repo",
  agentSkillRepoPath: "",
  skillDir: "/tmp/skill",
  userId: "user",
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
  vi.mocked(useParams).mockReturnValue({ workflowSessionId: "ws-1" });
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
      "/admin/workflows/wf-1"
    );
    expect(within(nav).getByText("Session")).toHaveAttribute("aria-current", "page");
  });

  it("falls back to a plain-text crumb when the session has no linked workflow", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-sessions/:id", () =>
        envelope({ ...WORKFLOW_SESSION_1, workflowId: null })
      )
    );
    render(<WorkflowSessionPage />, { preloadedState: AUTH_STATE });
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("My Workflow")).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "My Workflow" })).not.toBeInTheDocument();
  });
});
