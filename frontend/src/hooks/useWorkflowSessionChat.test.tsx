import { RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
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
  createPlanningSessionAgent: vi.fn(),
  createWorkflowSessionAgent: vi.fn(),
  getPlanningSessionMessages: vi.fn(),
  getWorkflowSessionMessages: vi.fn(),
  getWorkflowSessionMessageSenders: vi.fn(),
  getWorkflowSessionMessageTasks: vi.fn(),
  listWorkflowTasks: vi.fn(),
  getUsersByIds: vi.fn(),
  formatUserName: (u: { firstName: string; lastName: string }) => `${u.firstName} ${u.lastName}`,
}));

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
  vi.mocked(api.createPlanningSessionAgent).mockClear();
  vi.mocked(api.createPlanningSessionAgent).mockReturnValue(mockAgent as never);
  vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([]);
  vi.mocked(api.getPlanningSessionMessages).mockClear();
  vi.mocked(api.getPlanningSessionMessages).mockResolvedValue([]);
  vi.mocked(api.getWorkflowSessionMessageSenders).mockResolvedValue(new Map());
  vi.mocked(api.getWorkflowSessionMessageTasks).mockResolvedValue(new Map());
  vi.mocked(api.listWorkflowTasks).mockResolvedValue([]);
  vi.mocked(api.getUsersByIds).mockResolvedValue(new Map());
  mockAgent.addMessage.mockClear();
  mockAgent.runAgent.mockClear();
});

describe("useWorkflowSessionChat", () => {
  it("calls getWorkflowSessionMessages on mount with the workflow session id", async () => {
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getWorkflowSessionMessages).toHaveBeenCalledWith("ws-1"));
  });

  it("returns pendingRenderCalls mirroring the store", async () => {
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getWorkflowSessionMessages).toHaveBeenCalled());
    act(() => {
      store.dispatch(addPendingRenderCall({ toolCallId: "tc-1", surfaceId: "s1" }));
    });
    expect(result.current.pendingRenderCalls).toEqual([{ toolCallId: "tc-1", surfaceId: "s1" }]);
  });

  it("auto-sends workflowPrompt when messages are empty on mount", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() =>
      expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("ws-1", "sess-abc")
    );
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    const messages = store.getState().chat.messages;
    expect(messages.some((m) => m.role === "user" && m.content === "Do the thing")).toBe(true);
  });

  it("does NOT auto-send when kickoffPrompt is null (planning sessions)", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", null, "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getWorkflowSessionMessages).toHaveBeenCalled());
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
    expect(store.getState().chat.messages).toHaveLength(0);
  });

  it("planning variant reads and sends through the planning-session endpoints", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockClear();
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ps-1", "plan-sess", null, "owner-1", "planning"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getPlanningSessionMessages).toHaveBeenCalledWith("ps-1"));
    expect(api.getWorkflowSessionMessages).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.sendMessage("add a step");
    });
    expect(api.createPlanningSessionAgent).toHaveBeenCalledWith("ps-1", "plan-sess");
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("planning variant skips task and sender-attribution fetches", async () => {
    vi.mocked(api.listWorkflowTasks).mockClear();
    vi.mocked(api.getWorkflowSessionMessageTasks).mockClear();
    vi.mocked(api.getWorkflowSessionMessageSenders).mockClear();
    vi.mocked(api.getUsersByIds).mockClear();
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ps-1", "plan-sess", null, "owner-1", "planning"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getPlanningSessionMessages).toHaveBeenCalled());
    expect(api.listWorkflowTasks).not.toHaveBeenCalled();
    expect(api.getWorkflowSessionMessageTasks).not.toHaveBeenCalled();
    expect(api.getWorkflowSessionMessageSenders).not.toHaveBeenCalled();
    // The owner is still resolved, for the avatar fallback.
    await waitFor(() => expect(api.getUsersByIds).toHaveBeenCalledWith(["owner-1"]));
  });

  it("does NOT auto-send when messages already exist", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "previous message" },
    ]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getWorkflowSessionMessages).toHaveBeenCalled());
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("sendMessage uses createWorkflowSessionAgent with the correct ids", async () => {
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getWorkflowSessionMessages).toHaveBeenCalled());
    // Wait for auto-send to finish
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    mockAgent.runAgent.mockClear();
    vi.mocked(api.createWorkflowSessionAgent).mockClear();

    await result.current.sendMessage("hello");
    expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("ws-1", "sess-abc");
    expect(mockAgent.runAgent).toHaveBeenCalled();
  });

  it("sendA2uiAction posts the action as a tool result and resumes the run", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    store.dispatch(addPendingRenderCall({ toolCallId: "tc-a2ui-1", surfaceId: "s1" }));
    mockAgent.addMessage.mockClear();
    mockAgent.runAgent.mockClear();
    vi.mocked(api.getWorkflowSessionMessages).mockClear();

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
    expect(store.getState().chat.pendingRenderCalls).toEqual([]);
    expect(mockAgent.runAgent).toHaveBeenCalled();
    // The tool result is now persisted with its sender; the attribution map
    // is refreshed so the acted-on A2UI surface shows the right avatar.
    expect(api.getWorkflowSessionMessageSenders).toHaveBeenCalled();
    // The full history is re-fetched (not just the sender map) so the
    // resolved A2UI card's sourceToolCallId is re-derived from the same
    // persisted ids the sender map uses, instead of trusting the id streamed
    // live to the browser (which ADK can remap for long-running client tools).
    expect(api.getWorkflowSessionMessages).toHaveBeenCalledWith("ws-1");
  });

  it("sendA2uiAction targets the acted-on surface and no-op acks the rest", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
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
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
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
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
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
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValueOnce([
      { id: "m1", role: "user", content: "existing" },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
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
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
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
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    mockAgent.addMessage.mockClear();
    mockAgent.runAgent.mockClear();
    vi.mocked(api.getWorkflowSessionMessageSenders).mockClear();

    await result.current.sendApprovalResult("tool-call-1", "approved");

    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "tool", toolCallId: "tool-call-1", content: "approved" })
    );
    expect(mockAgent.runAgent).toHaveBeenCalled();
    // The decision is now persisted with its sender; the attribution map is
    // refreshed so the approval bubble shows the decider's avatar right away.
    expect(api.getWorkflowSessionMessageSenders).toHaveBeenCalledWith("ws-1");
  });

  it("exposes resolved message senders loaded on mount", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    vi.mocked(api.getWorkflowSessionMessageSenders).mockResolvedValue(new Map([["m1", "alice"]]));
    vi.mocked(api.getUsersByIds).mockResolvedValue(
      new Map([["alice", { id: "alice", username: "alice" } as never]])
    );
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getWorkflowSessionMessageSenders).toHaveBeenCalledWith("ws-1"));
    await waitFor(() => expect(result.current.messageSenders.get("m1")).toBe("alice"));
    expect(api.getUsersByIds).toHaveBeenCalledWith(["owner-1", "alice"]);
    expect(result.current.senderUsers.get("alice")?.username).toBe("alice");
  });

  it("dispatches setError when runAgent throws during sendMessage", async () => {
    vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    mockAgent.runAgent.mockRejectedValueOnce(new Error("stream failure"));
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
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
    vi.mocked(api.getWorkflowSessionMessages).mockClear().mockResolvedValue([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <StrictMode>
          <Provider store={store}>{children}</Provider>
        </StrictMode>
      ),
    });
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalledTimes(1));
    // The guard makes the repeat mount run a no-op: only one history load, and
    // the optimistic prompt survives (exactly one bubble, not wiped).
    expect(vi.mocked(api.getWorkflowSessionMessages)).toHaveBeenCalledTimes(1);
    const prompts = store
      .getState()
      .chat.messages.filter((m) => m.role === "user" && m.content === "Do the thing");
    expect(prompts).toHaveLength(1);
  });

  describe("polling", () => {
    it("re-fetches messages on the polling interval", async () => {
      vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
        { id: "m1", role: "user", content: "existing" },
      ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
          wrapper: makeWrapper(store),
        });
        // Flush the mount load (no auto-send: messages already exist).
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const afterMount = vi.mocked(api.getWorkflowSessionMessages).mock.calls.length;
        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(vi.mocked(api.getWorkflowSessionMessages).mock.calls.length).toBeGreaterThan(
          afterMount
        );
      } finally {
        vi.useRealTimers();
      }
    });

    it("applies messages a poll discovers from another participant", async () => {
      vi.mocked(api.getWorkflowSessionMessages)
        .mockResolvedValueOnce([{ id: "m1", role: "user", content: "mine" }])
        .mockResolvedValue([
          { id: "m1", role: "user", content: "mine" },
          { id: "m2", role: "user", content: "from someone else" },
        ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
          wrapper: makeWrapper(store),
        });
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        expect(store.getState().chat.messages).toHaveLength(1);
        const sendersBefore = vi.mocked(api.getWorkflowSessionMessageSenders).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(store.getState().chat.messages).toHaveLength(2);
        // The changed history triggers a sender refresh so avatars stay in sync.
        expect(vi.mocked(api.getWorkflowSessionMessageSenders).mock.calls.length).toBeGreaterThan(
          sendersBefore
        );
      } finally {
        vi.useRealTimers();
      }
    });

    it("skips re-applying an unchanged history", async () => {
      vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
        { id: "m1", role: "user", content: "existing" },
      ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
          wrapper: makeWrapper(store),
        });
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const sendersBefore = vi.mocked(api.getWorkflowSessionMessageSenders).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        // Same length + last id: no resumeSession, no extra sender refresh.
        expect(store.getState().chat.messages).toHaveLength(1);
        expect(vi.mocked(api.getWorkflowSessionMessageSenders).mock.calls.length).toBe(
          sendersBefore
        );
      } finally {
        vi.useRealTimers();
      }
    });

    it("does not poll while the viewer's own run is in flight", async () => {
      vi.mocked(api.getWorkflowSessionMessages).mockResolvedValue([
        { id: "m1", role: "user", content: "existing" },
      ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        const { result } = renderHook(
          () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"),
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
        const fetchesBefore = vi.mocked(api.getWorkflowSessionMessages).mock.calls.length;

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });
        expect(vi.mocked(api.getWorkflowSessionMessages).mock.calls.length).toBe(fetchesBefore);
      } finally {
        vi.useRealTimers();
      }
    });

    it("keeps the auto-sent prompt in place (stable id) across the first poll", async () => {
      // Mount finds an empty history (auto-sends the prompt); the first poll then
      // returns the persisted prompt under a different, ADK-assigned id. The
      // optimistic bubble must not be remounted, so its id stays put and it is
      // not duplicated.
      vi.mocked(api.getWorkflowSessionMessages)
        .mockResolvedValueOnce([])
        .mockResolvedValue([
          { id: "adk-u", role: "user", content: "Do the thing" },
          { id: "adk-a", role: "assistant", content: "on it" },
        ]);
      vi.useFakeTimers();
      try {
        const store = makeStore();
        renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing", "owner-1"), {
          wrapper: makeWrapper(store),
        });
        // Flush the mount load + auto-send + (immediately resolving) run.
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0);
        });
        const optimistic = store
          .getState()
          .chat.messages.find((m) => m.role === "user" && m.content === "Do the thing");
        expect(optimistic).toBeDefined();
        const optimisticId = optimistic?.id;
        expect(optimisticId).not.toBe("adk-u");

        await act(async () => {
          await vi.advanceTimersByTimeAsync(10_000);
        });

        const messages = store.getState().chat.messages;
        // Exactly one prompt bubble, still under its optimistic id (no remount).
        const prompts = messages.filter((m) => m.role === "user" && m.content === "Do the thing");
        expect(prompts).toHaveLength(1);
        expect(prompts[0].id).toBe(optimisticId);
        // The polled assistant reply is now shown too.
        expect(messages.some((m) => m.role === "assistant" && m.content === "on it")).toBe(true);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
