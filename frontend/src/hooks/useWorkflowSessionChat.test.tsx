import { RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type ReactNode, StrictMode } from "react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { formatActionContent, RENDER_ACK_CONTENT } from "@/lib/a2uiAction";
import * as api from "@/lib/api";
import { addPendingRenderCall } from "@/store/chatSlice";
import { makeStore } from "@/test/test-utils";
import { useWorkflowSessionChat } from "./useWorkflowSessionChat";

vi.mock("@/lib/api", () => ({
  createDesignSessionAgent: vi.fn(),
  createWorkflowSessionAgent: vi.fn(),
  getDesignSessionHistory: vi.fn(),
  getWorkflowSessionHistory: vi.fn(),
  isForbiddenError: vi.fn(),
  listWorkflowTasks: vi.fn(),
  getUsersByIds: vi.fn(),
  SUPPRESS_FORBIDDEN_TOAST: { suppressForbiddenToast: true },
  formatUserName: (u: { firstName: string; lastName: string }) => `${u.firstName} ${u.lastName}`,
}));

/** Build the `/messages` payload the history endpoints return. */
function history(
  messages: Message[],
  senders = new Map<string, string>(),
  tasks = new Map<string, string>()
): api.SessionHistory {
  return { messages, senders, tasks };
}

/** Point the workflow-session history mock at a history, for every call. */
function mockWorkflowHistory(
  messages: Message[],
  senders?: Map<string, string>,
  tasks?: Map<string, string>
) {
  vi.mocked(api.getWorkflowSessionHistory).mockResolvedValue(history(messages, senders, tasks));
}

/** Point the workflow-session history mock at a history, for the next call only. */
function mockWorkflowHistoryOnce(
  messages: Message[],
  senders?: Map<string, string>,
  tasks?: Map<string, string>
) {
  vi.mocked(api.getWorkflowSessionHistory).mockResolvedValueOnce(history(messages, senders, tasks));
}

/** Point the design-session history mock at a history, for every call. */
function mockDesignHistory(messages: Message[], senders?: Map<string, string>) {
  vi.mocked(api.getDesignSessionHistory).mockResolvedValue(history(messages, senders));
}

const mockAgent = {
  addMessage: vi.fn(),
  runAgent: vi.fn().mockResolvedValue(undefined),
  use: vi.fn(),
};

function makeWrapper(store: ReturnType<typeof makeStore>) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  };
}

beforeEach(() => {
  vi.mocked(api.createWorkflowSessionAgent).mockClear();
  vi.mocked(api.createWorkflowSessionAgent).mockReturnValue(mockAgent as never);
  vi.mocked(api.createDesignSessionAgent).mockClear();
  vi.mocked(api.createDesignSessionAgent).mockReturnValue(mockAgent as never);
  mockWorkflowHistory([]);
  vi.mocked(api.getDesignSessionHistory).mockClear();
  mockDesignHistory([]);
  vi.mocked(api.listWorkflowTasks).mockClear();
  vi.mocked(api.listWorkflowTasks).mockResolvedValue([]);
  vi.mocked(api.getUsersByIds).mockClear();
  vi.mocked(api.getUsersByIds).mockResolvedValue(new Map());
  vi.mocked(api.isForbiddenError).mockReset().mockReturnValue(false);
  mockAgent.addMessage.mockClear();
  mockAgent.runAgent.mockClear();
});

describe("useWorkflowSessionChat", () => {
  it("calls getWorkflowSessionHistory on mount with the workflow execution id", async () => {
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() =>
      expect(api.getWorkflowSessionHistory).toHaveBeenCalledWith(
        "execution-1",
        api.SUPPRESS_FORBIDDEN_TOAST
      )
    );
  });

  it("returns pendingRenderCalls mirroring the store", async () => {
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getWorkflowSessionHistory).toHaveBeenCalled());
    act(() => {
      store.dispatch(addPendingRenderCall({ toolCallId: "tc-1", surfaceId: "s1" }));
    });
    expect(result.current.pendingRenderCalls).toEqual([{ toolCallId: "tc-1", surfaceId: "s1" }]);
  });

  it("auto-sends workflowPrompt when messages are empty on mount", async () => {
    mockWorkflowHistory([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() =>
      expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("execution-1", "sess-abc")
    );
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    const messages = store.getState().chat.messages;
    expect(messages.some((m) => m.role === "user" && m.content === "Do the thing")).toBe(true);
  });

  it("does NOT auto-send when kickoffPrompt is null (design sessions)", async () => {
    mockWorkflowHistory([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("execution-1", "sess-abc", null, "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getWorkflowSessionHistory).toHaveBeenCalled());
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
    expect(store.getState().chat.messages).toHaveLength(0);
  });

  it("design variant reads and sends through the design-session endpoints", async () => {
    vi.mocked(api.getWorkflowSessionHistory).mockClear();
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ds-1", "design-sess", null, "owner-1", "design"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() =>
      expect(api.getDesignSessionHistory).toHaveBeenCalledWith("ds-1", api.SUPPRESS_FORBIDDEN_TOAST)
    );
    expect(api.getWorkflowSessionHistory).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.sendMessage("add a step");
    });
    expect(api.createDesignSessionAgent).toHaveBeenCalledWith("ds-1", "design-sess");
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("design variant skips task fetches but still loads sender attribution", async () => {
    // The design chat is shared by the tenant's developers, so it is attributed
    // through its own endpoint — but it has no status-ful tasks to associate.
    mockDesignHistory([], new Map([["m1", "developer-2"]]));
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ds-1", "design-sess", null, "owner-1", "design"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getDesignSessionHistory).toHaveBeenCalled());
    expect(api.listWorkflowTasks).not.toHaveBeenCalled();
    expect(api.getWorkflowSessionHistory).not.toHaveBeenCalled();
    // The owner is resolved alongside the senders, for the avatar fallback.
    await waitFor(() => expect(api.getUsersByIds).toHaveBeenCalledWith(["owner-1", "developer-2"]));
  });

  it("design variant exposes the resolved senders for avatar rendering", async () => {
    const sender = {
      id: "developer-2",
      username: "dev2",
      firstName: "Dev",
      lastName: "Two",
    } as never;
    mockDesignHistory([], new Map([["m1", "developer-2"]]));
    vi.mocked(api.getUsersByIds).mockResolvedValue(new Map([["developer-2", sender]]));
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ds-1", "design-sess", null, "owner-1", "design"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(result.current.messageSenders.get("m1")).toBe("developer-2"));
    expect(result.current.senderUsers.get("developer-2")).toBe(sender);
  });

  it("does NOT auto-send when messages already exist", async () => {
    mockWorkflowHistory([{ id: "m1", role: "user", content: "previous message" }]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getWorkflowSessionHistory).toHaveBeenCalled());
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("sets forbidden and does not auto-send when the initial fetch is FORBIDDEN", async () => {
    vi.mocked(api.getWorkflowSessionHistory).mockRejectedValue(new Error("forbidden"));
    vi.mocked(api.isForbiddenError).mockReturnValue(true);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(result.current.forbidden).toBe(true));
    // A FORBIDDEN failure must not be treated as "no session yet" -- it must
    // not auto-send the kickoff prompt and start an unauthorized run.
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("sets forbidden for the design variant without treating it as a new session", async () => {
    vi.mocked(api.getDesignSessionHistory).mockRejectedValue(new Error("forbidden"));
    vi.mocked(api.isForbiddenError).mockReturnValue(true);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ds-1", "design-sess", null, "owner-1", "design"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(result.current.forbidden).toBe(true));
    expect(api.createDesignSessionAgent).not.toHaveBeenCalled();
  });

  it("sendMessage uses createWorkflowSessionAgent with the correct ids", async () => {
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getWorkflowSessionHistory).toHaveBeenCalled());
    // Wait for auto-send to finish
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    mockAgent.runAgent.mockClear();
    vi.mocked(api.createWorkflowSessionAgent).mockClear();

    await result.current.sendMessage("hello");
    expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("execution-1", "sess-abc");
    expect(mockAgent.runAgent).toHaveBeenCalled();
  });

  it("sendA2uiAction posts the action as a tool result and resumes the run", async () => {
    mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    store.dispatch(addPendingRenderCall({ toolCallId: "tc-a2ui-1", surfaceId: "s1" }));
    mockAgent.addMessage.mockClear();
    mockAgent.runAgent.mockClear();
    vi.mocked(api.getWorkflowSessionHistory).mockClear();

    const action = { name: "click", surfaceId: "s1", sourceComponentId: "btn1", context: {} };
    const values = { email: "a@b.c" };
    await result.current.sendA2uiAction(action, values);

    // The surface's data model rides along, so the agent sees what the user
    // entered and a reloaded session can be redisplayed pre-filled.
    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "tool",
        toolCallId: "tc-a2ui-1",
        content: formatActionContent(action, values),
      })
    );
    // The tool result is preceded by an assistant message re-declaring the
    // render_a2ui call: ag-ui-adk resolves the FunctionResponse's function name
    // from it, and names it "unknown" (which the provider rejects) without it.
    const sent = mockAgent.addMessage.mock.calls.map(([m]) => m as { role: string });
    expect(sent[0]).toMatchObject({
      role: "assistant",
      toolCalls: [{ id: "tc-a2ui-1", function: { name: RENDER_A2UI_TOOL_NAME } }],
    });
    expect(sent[1]).toMatchObject({ role: "tool" });
    expect(store.getState().chat.pendingRenderCalls).toEqual([]);
    expect(mockAgent.runAgent).toHaveBeenCalled();
    // The full history is re-fetched — carrying the sender attribution with it,
    // so the acted-on A2UI surface shows the right avatar — and the resolved
    // card's sourceToolCallId is re-derived from the same persisted ids rather
    // than the one streamed live to the browser (which ADK can remap for
    // long-running client tools).
    expect(api.getWorkflowSessionHistory).toHaveBeenCalledWith("execution-1");
  });

  it("sendA2uiAction targets the acted-on surface and no-op acks the rest", async () => {
    mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    // Two surfaces pending: a display-only one and the one the user acts on.
    store.dispatch(addPendingRenderCall({ toolCallId: "tc-display", surfaceId: "s-display" }));
    store.dispatch(addPendingRenderCall({ toolCallId: "tc-acted", surfaceId: "s-acted" }));
    mockAgent.addMessage.mockClear();

    const action = { name: "click", surfaceId: "s-acted", sourceComponentId: "btn1", context: {} };
    const values = { email: "a@b.c" };
    await result.current.sendA2uiAction(action, values);

    // Only the acted-on call carries the action; the display-only surface gets
    // the no-op ack the backend skips when attributing senders.
    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({ toolCallId: "tc-display", content: RENDER_ACK_CONTENT })
    );
    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        toolCallId: "tc-acted",
        content: formatActionContent(action, values),
      })
    );
  });

  it("sendA2uiAction acknowledges render calls derived from the loaded history", async () => {
    // After a page reload (or when another participant's run rendered the
    // surface), no live stream ever added the pending call — it must be
    // re-derived from the persisted history so the action is not dropped.
    mockWorkflowHistory([
      {
        id: "m1",
        role: "assistant",
        content: "",
        toolCalls: [
          {
            id: "tc-from-history",
            type: "function",
            function: {
              name: RENDER_A2UI_TOOL_NAME,
              arguments: JSON.stringify({ surfaceId: "s1", components: [] }),
            },
          },
        ],
      },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() =>
      expect(store.getState().chat.pendingRenderCalls).toEqual([
        { toolCallId: "tc-from-history", surfaceId: "s1" },
      ])
    );
    mockAgent.addMessage.mockClear();

    const action = { name: "click", surfaceId: "s1", sourceComponentId: "btn1", context: {} };
    const values = { email: "a@b.c" };
    await result.current.sendA2uiAction(action, values);

    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "tool",
        toolCallId: "tc-from-history",
        content: formatActionContent(action, values),
      })
    );
  });

  it("re-derives pending render calls from the resynced history after sendA2uiAction", async () => {
    // If the agent's response to the acknowledgment immediately renders a
    // follow-up A2UI surface, the post-run resync replaces the live-streamed
    // pending id with the one persisted in the history (ADK can remap
    // long-running client-tool ids between the streamed and persisted events).
    mockWorkflowHistoryOnce([{ id: "m1", role: "user", content: "existing" }]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    store.dispatch(addPendingRenderCall({ toolCallId: "tc-a2ui-1", surfaceId: "s1" }));

    mockAgent.runAgent.mockImplementationOnce(async () => {
      // Simulate the follow-up render_a2ui call ending mid-run, before the
      // resync fires.
      store.dispatch(addPendingRenderCall({ toolCallId: "tc-a2ui-2-live", surfaceId: "s2" }));
    });
    // The resync returns the persisted history: the acted-on call is answered,
    // the follow-up render call is not (and carries its persisted id).
    mockWorkflowHistory([
      { id: "m1", role: "user", content: "existing" },
      { id: "t1", role: "tool", toolCallId: "tc-a2ui-1", content: "acted" },
      {
        id: "m2",
        role: "assistant",
        content: "",
        toolCalls: [
          {
            id: "tc-a2ui-2-persisted",
            type: "function",
            function: {
              name: RENDER_A2UI_TOOL_NAME,
              arguments: JSON.stringify({ surfaceId: "s2", components: [] }),
            },
          },
        ],
      },
    ]);

    await result.current.sendA2uiAction(
      { name: "click", surfaceId: "s1", sourceComponentId: "btn1", context: {} },
      {}
    );

    await waitFor(() =>
      expect(store.getState().chat.pendingRenderCalls).toEqual([
        { toolCallId: "tc-a2ui-2-persisted", surfaceId: "s2" },
      ])
    );
  });

  it("sendApprovalResult posts the decision as a tool result and resumes the run", async () => {
    mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    mockAgent.addMessage.mockClear();
    mockAgent.runAgent.mockClear();
    vi.mocked(api.getWorkflowSessionHistory).mockClear();

    await result.current.sendApprovalResult("tool-call-1", "approved");

    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "tool", toolCallId: "tool-call-1", content: "approved" })
    );
    // Same carrier requirement as the A2UI acks, under the approval tool's name.
    const sent = mockAgent.addMessage.mock.calls.map(([m]) => m as { role: string });
    expect(sent[0]).toMatchObject({
      role: "assistant",
      toolCalls: [{ id: "tool-call-1", function: { name: "render_approval" } }],
    });
    expect(sent[1]).toMatchObject({ role: "tool" });
    expect(mockAgent.runAgent).toHaveBeenCalled();
    // The decision is now persisted with its sender; the history is re-read so
    // the approval bubble shows the decider's avatar right away.
    expect(api.getWorkflowSessionHistory).toHaveBeenCalledWith("execution-1");
  });

  it("exposes resolved message senders loaded on mount", async () => {
    mockWorkflowHistory(
      [{ id: "m1", role: "user", content: "existing" }],
      new Map([["m1", "alice"]])
    );
    vi.mocked(api.getUsersByIds).mockResolvedValue(
      new Map([["alice", { id: "alice", username: "alice" } as never]])
    );
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(result.current.messageSenders.get("m1")).toBe("alice"));
    expect(api.getUsersByIds).toHaveBeenCalledWith(["owner-1", "alice"]);
    expect(result.current.senderUsers.get("alice")?.username).toBe("alice");
  });

  it("dispatches setError when runAgent throws during sendMessage", async () => {
    mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
    mockAgent.runAgent.mockRejectedValueOnce(new Error("stream failure"));
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    await result.current.sendMessage("hi");
    await waitFor(() => expect(store.getState().chat.error).not.toBeNull());
  });

  it("keeps the auto-sent prompt when the mount effect re-runs (StrictMode)", async () => {
    // StrictMode mounts, unmounts, then remounts in development, re-invoking the
    // mount effect. Its second run must not clear the freshly auto-sent prompt,
    // so the workflow prompt does not vanish before the first poll.
    // beforeEach does not clear this mock's call count, so reset it here to
    // count only this test's history loads.
    vi.mocked(api.getWorkflowSessionHistory).mockClear();
    mockWorkflowHistory([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <StrictMode>
          <Provider store={store}>{children}</Provider>
        </StrictMode>
      ),
    });
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalledTimes(1));
    // The guard makes the repeat mount run a no-op: the initial load (the only
    // one made with the forbidden-toast suppressed) happens once, and the
    // optimistic prompt survives (exactly one bubble, not wiped).
    const initialLoads = vi
      .mocked(api.getWorkflowSessionHistory)
      .mock.calls.filter(([, config]) => config === api.SUPPRESS_FORBIDDEN_TOAST);
    expect(initialLoads).toHaveLength(1);
    const prompts = store
      .getState()
      .chat.messages.filter((m) => m.role === "user" && m.content === "Do the thing");
    expect(prompts).toHaveLength(1);
  });

  describe("polling", () => {
    it("re-fetches messages on the polling interval", async () => {
      mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
          {
            wrapper: makeWrapper(store),
          }
        );
        // Flush the mount load (no auto-send: messages already exist).
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const afterMount = vi.mocked(api.getWorkflowSessionHistory).mock.calls.length;
        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(vi.mocked(api.getWorkflowSessionHistory).mock.calls.length).toBeGreaterThan(
          afterMount
        );
      } finally {
        vi.useRealTimers();
      }
    });

    it("applies messages a poll discovers from another participant", async () => {
      mockWorkflowHistoryOnce([{ id: "m1", role: "user", content: "mine" }]);
      mockWorkflowHistory([
        { id: "m1", role: "user", content: "mine" },
        { id: "m2", role: "user", content: "from someone else" },
      ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
          {
            wrapper: makeWrapper(store),
          }
        );
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        expect(store.getState().chat.messages).toHaveLength(1);
        const usersBefore = vi.mocked(api.getUsersByIds).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(store.getState().chat.messages).toHaveLength(2);
        // A changed history re-resolves the senders so avatars stay in sync.
        expect(vi.mocked(api.getUsersByIds).mock.calls.length).toBeGreaterThan(usersBefore);
      } finally {
        vi.useRealTimers();
      }
    });

    it("skips re-applying an unchanged history", async () => {
      mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
          {
            wrapper: makeWrapper(store),
          }
        );
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const usersBefore = vi.mocked(api.getUsersByIds).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        // Same length + last stable id: nothing re-applied, no extra fetches.
        expect(store.getState().chat.messages).toHaveLength(1);
        expect(vi.mocked(api.getUsersByIds).mock.calls.length).toBe(usersBefore);
      } finally {
        vi.useRealTimers();
      }
    });

    it("re-applies the history on the poll after a run, so late attribution lands", async () => {
      // The backend records sender attribution and task association after the
      // stream's last event, so the resync that follows a run can read the
      // history before either exists. The next poll has to apply it again even
      // though the messages themselves are unchanged — otherwise the miss stays
      // frozen until a reload, showing the run under the previous task.
      const persisted: Message[] = [
        { id: "adk-u", role: "user", content: "hi" },
        { id: "adk-a", role: "assistant", content: "hello" },
      ];
      mockWorkflowHistoryOnce([]); // mount: empty session
      mockWorkflowHistoryOnce(persisted); // post-run resync: attribution not written yet
      mockWorkflowHistory(persisted, new Map([["adk-u", "alice"]]), new Map([["adk-u", "task-1"]]));
      vi.useFakeTimers();
      try {
        const store = makeStore();
        const { result } = renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", null, "owner-1"),
          { wrapper: makeWrapper(store) }
        );
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        await act(async () => {
          await result.current.sendMessage("hi");
        });
        expect(result.current.messageSenders.size).toBe(0);

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(result.current.messageSenders.get("adk-u")).toBe("alice");
        expect(result.current.messageTasks.get("adk-u")).toBe("task-1");
      } finally {
        vi.useRealTimers();
      }
    });

    it("does not poll while the viewer's own run is in flight", async () => {
      mockWorkflowHistory([{ id: "m1", role: "user", content: "existing" }]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        const { result } = renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
          { wrapper: makeWrapper(store) }
        );
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        // Start a run that never resolves so isRunning stays true across the tick.
        mockAgent.runAgent.mockImplementationOnce(() => new Promise<void>(() => {}));
        act(() => {
          void result.current.sendMessage("hi");
        });
        const fetchesBefore = vi.mocked(api.getWorkflowSessionHistory).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(vi.mocked(api.getWorkflowSessionHistory).mock.calls.length).toBe(fetchesBefore);
      } finally {
        vi.useRealTimers();
      }
    });

    it("keeps the auto-sent prompt's bubble in place across the first poll", async () => {
      // Mount finds an empty history (auto-sends the prompt); the first poll then
      // returns the persisted prompt under a different, ADK-assigned id. The
      // message takes that persisted id (the attribution maps are keyed by it)
      // while its bubble keeps the key it was drawn under, so it is neither
      // remounted nor duplicated.
      mockWorkflowHistoryOnce([]);
      mockWorkflowHistory([
        { id: "adk-u", role: "user", content: "Do the thing" },
        { id: "adk-a", role: "assistant", content: "on it" },
      ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(
          () => useWorkflowSessionChat("execution-1", "sess-abc", "Do the thing", "owner-1"),
          {
            wrapper: makeWrapper(store),
          }
        );
        // Flush the mount load + auto-send + (immediately resolving) run, whose
        // own resync is the first fetch to return the persisted history.
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const reconciled = store
          .getState()
          .chat.messages.filter((m) => m.role === "user" && m.content === "Do the thing");
        // One bubble, now under the persisted id but still keyed on the
        // optimistic one, so React never remounted it.
        expect(reconciled).toHaveLength(1);
        expect(reconciled[0].id).toBe("adk-u");
        const renderKey = reconciled[0].renderKey;
        expect(renderKey).toBeDefined();
        expect(renderKey).not.toBe("adk-u");

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });

        const messages = store.getState().chat.messages;
        const prompts = messages.filter((m) => m.role === "user" && m.content === "Do the thing");
        // The next poll must not undo that: the key is carried forward by id.
        expect(prompts).toHaveLength(1);
        expect(prompts[0].id).toBe("adk-u");
        expect(prompts[0].renderKey).toBe(renderKey);
        // The polled assistant reply is shown too.
        expect(messages.some((m) => m.role === "assistant" && m.content === "on it")).toBe(true);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
