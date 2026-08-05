import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { act, render, screen, waitFor, within } from "@/test/test-utils";
import DesignSessionPage from "./page";

/** Matches the page's own workflow poll interval. */
const WORKFLOW_POLL_INTERVAL_MS = 2000;

/** The default `/workflows/wf-1` handler's payload, for `server.use` overrides. */
const WORKFLOW_1 = {
  id: "wf-1",
  tenantId: "tenant-1",
  name: "my-workflow",
  description: null,
  generatedDescription: null,
  agentSkillId: "skill-1",
  status: "published",
  generationError: null,
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
  ChatInput: ({ leading }: { leading?: ReactNode }) => (
    <div data-testid="chat-input-mock">{leading}</div>
  ),
}));

/** Builds a preloaded auth slice with the given roles, so AuthProvider renders its children immediately. */
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

/**
 * Overrides the global `/auth/me` handler so the session keeps the given
 * roles. `AuthProvider` re-fetches the current user on mount and overwrites
 * the preloaded auth state with whatever it resolves — the default handler's
 * user carries no roles at all, which would otherwise reset `canEdit` to
 * false moments after the initial render.
 */
function mockMe(roles: string[]) {
  server.use(
    http.get("http://localhost:8000/api/v1/auth/me", () =>
      envelope({
        user: {
          id: "user-1",
          username: "alice",
          firstName: "Alice",
          lastName: "Smith",
          email: "alice@example.com",
          enabled: true,
          emailVerified: false,
          roles,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        },
        impersonatedBy: null,
      })
    )
  );
}

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ designSessionId: "ds-1" });
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

describe("DesignSessionPage", () => {
  it("renders a breadcrumb trail ending in Design, with the workflow name linking back to it", async () => {
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const nav = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByRole("link", { name: "my-workflow" })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1"
    );
    expect(within(nav).getByText("Design")).toHaveAttribute("aria-current", "page");
  });

  it("drives the chat hook in design mode with no kickoff prompt", async () => {
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    await screen.findByRole("link", { name: "my-workflow" });
    expect(useWorkflowSessionChatMock).toHaveBeenCalledWith(
      "ds-1",
      "design-session-id",
      null,
      "user",
      "design"
    );
  });

  it("renders the template timeline entries", async () => {
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
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
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    await waitFor(() => expect(screen.getByText("Template Step 1")).toBeInTheDocument());
    expect(screen.getByLabelText("1 bound tool")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("1 bound tool"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("search")).toBeInTheDocument();
    expect(await within(dialog).findByText("my-mcp-server")).toBeInTheDocument();
  });

  it("shows the chat actions menu for a developer", async () => {
    mockMe(["developer"]);
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    expect(
      await within(chatInputMock).findByRole("button", { name: "Chat actions" })
    ).toBeInTheDocument();
  });

  it("hides the chat actions menu for a non-developer", async () => {
    mockMe(["requester"]);
    render(<DesignSessionPage />, { preloadedState: authState(["requester"]) });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    await screen.findByRole("link", { name: "my-workflow" });
    expect(
      within(chatInputMock).queryByRole("button", { name: "Chat actions" })
    ).not.toBeInTheDocument();
  });

  it("generates a description, shows a toast, and opens the diff preview", async () => {
    mockMe(["developer"]);
    const { store } = render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    const menuTrigger = await within(chatInputMock).findByRole("button", {
      name: "Chat actions",
    });

    await userEvent.click(menuTrigger);
    await userEvent.click(screen.getByRole("menuitem", { name: /Generate description/ }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Description generated",
      })
    );
    const dialog = await screen.findByRole("dialog", { name: "Description diff" });
    // WORKFLOW_1's `description` stays null after generation (only
    // `generatedDescription` is set), so the dialog falls back to its
    // empty-description copy instead of rendering a word-level diff.
    expect(within(dialog).getByText(/Description is empty/)).toBeInTheDocument();
  });

  it("opens the diff dialog immediately with a loading skeleton, then swaps in the diff", async () => {
    mockMe(["developer"]);
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/generate-description", async () => {
        // Outlast useAsyncAction's 200ms pending gate so the loading state is reached.
        await delay(400);
        return envelope({ ...WORKFLOW_1, generatedDescription: "A freshly generated summary" });
      })
    );
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    const menuTrigger = await within(chatInputMock).findByRole("button", {
      name: "Chat actions",
    });

    await userEvent.click(menuTrigger);
    await userEvent.click(screen.getByRole("menuitem", { name: /Generate description/ }));

    // The dialog opens right away, while the request is still in flight.
    const dialog = await screen.findByRole("dialog", { name: "Description diff" });
    expect(within(dialog).getByRole("status", { name: "Generating" })).toBeInTheDocument();
    await waitFor(() => expect(dialog).toHaveClass("live-edge"));

    // Once the request resolves, the skeleton is replaced by the diff content.
    await waitFor(() =>
      expect(within(dialog).queryByRole("status", { name: "Generating" })).not.toBeInTheDocument()
    );
    expect(dialog).not.toHaveClass("live-edge");
    expect(within(dialog).getByText(/Description is empty/)).toBeInTheDocument();
  });

  it("closes the diff dialog if generating the description fails", async () => {
    mockMe(["developer"]);
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/generate-description", () =>
        envelopeErr("INTERNAL", "Something went wrong", 500)
      )
    );
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    const menuTrigger = await within(chatInputMock).findByRole("button", {
      name: "Chat actions",
    });

    await userEvent.click(menuTrigger);
    await userEvent.click(screen.getByRole("menuitem", { name: /Generate description/ }));

    await screen.findByRole("dialog", { name: "Description diff" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Description diff" })).not.toBeInTheDocument()
    );
  });

  it("disables the generate-description item while the workflow is generating", async () => {
    mockMe(["developer"]);
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: null,
          agentSkillId: "skill-1",
          status: "generating",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    const chatInputMock = await screen.findByTestId("chat-input-mock");
    const menuTrigger = await within(chatInputMock).findByRole("button", {
      name: "Chat actions",
    });

    await userEvent.click(menuTrigger);

    expect(screen.getByRole("menuitem", { name: /Generate description/ })).toBeDisabled();
  });

  it("shows the reason a background design run failed", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          ...WORKFLOW_1,
          status: "failed",
          generationError: "The design agent run failed (EXECUTION_TIMEOUT).",
        })
      )
    );
    render(<DesignSessionPage />, { preloadedState: AUTH_STATE });

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(
      "Workflow generation failed: The design agent run failed (EXECUTION_TIMEOUT)."
    );
    // The failure is the workflow's state, not a dismissible one-off event.
    expect(within(banner).queryByRole("button", { name: "Dismiss error" })).toBeNull();
  });

  it("drops the failure banner once a turn repairs the design", async () => {
    // A template write recovers the workflow to `draft` server-side, so the
    // page has to re-read it when the turn ends — otherwise the banner keeps
    // reporting a failure the user has just fixed.
    let calls = 0;
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () => {
        calls += 1;
        return calls === 1
          ? envelope({
              ...WORKFLOW_1,
              status: "failed",
              generationError: "The design run registered no task templates.",
            })
          : envelope({ ...WORKFLOW_1, status: "draft" });
      })
    );

    const { rerender } = render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
    await screen.findByRole("alert");

    // A turn runs...
    useWorkflowSessionChatMock.mockReturnValue({
      ...useWorkflowSessionChatMock(),
      isRunning: true,
    });
    rerender(<DesignSessionPage />);
    // ...and finishes.
    useWorkflowSessionChatMock.mockReturnValue({
      ...useWorkflowSessionChatMock(),
      isRunning: false,
    });
    rerender(<DesignSessionPage />);

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("surfaces a failure that lands while the page is already open", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let calls = 0;
      server.use(
        http.get("http://localhost:8000/api/v1/workflows/:id", () => {
          calls += 1;
          return calls === 1
            ? envelope({ ...WORKFLOW_1, status: "generating" })
            : envelope({
                ...WORKFLOW_1,
                status: "failed",
                generationError: "The design run registered no task templates.",
              });
        })
      );

      render(<DesignSessionPage />, { preloadedState: AUTH_STATE });
      await screen.findByTestId("message-list-mock");
      expect(screen.queryByRole("alert")).toBeNull();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(WORKFLOW_POLL_INTERVAL_MS);
      });

      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Workflow generation failed: The design run registered no task templates."
        )
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
