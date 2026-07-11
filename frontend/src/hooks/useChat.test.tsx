import { RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import type { AgentSubscriber } from "@ag-ui/client";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { startRun } from "@/store/chatSlice";
import { makeStore } from "@/test/test-utils";
import { useChat } from "./useChat";

vi.mock("@/lib/api", () => ({
  createChatAgent: vi.fn(),
  getSessionMessages: vi.fn(),
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

async function waitForInit(store: ReturnType<typeof makeStore>) {
  await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalled());
  await waitFor(() => expect(store.getState().chat.sessionId).toBe("sess-abc"));
}

beforeEach(() => {
  vi.mocked(api.createChatAgent).mockClear();
  vi.mocked(api.createChatAgent).mockReturnValue(mockAgent as never);
  vi.mocked(api.getSessionMessages).mockClear();
  vi.mocked(api.getSessionMessages).mockResolvedValue([]);
  mockAgent.addMessage.mockClear();
  mockAgent.runAgent.mockClear();
});

describe("useChat", () => {
  it("dispatches setSession on mount", () => {
    const store = makeStore();
    renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    expect(store.getState().chat.sessionId).toBe("sess-abc");
  });

  it("calls getSessionMessages on mount", async () => {
    const store = makeStore();
    renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalledWith("sess-abc"));
  });

  it("dispatches resumeSession after getSessionMessages resolves", async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "hello" },
    ]);
    const store = makeStore();
    renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
  });

  it("sendMessage does nothing when isRunning is true", async () => {
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    act(() => {
      store.dispatch(startRun());
    });
    await result.current.sendMessage("hello");
    expect(api.createChatAgent).not.toHaveBeenCalled();
  });

  it("sendMessage dispatches addUserMessage, calls runAgent, dispatches finishRun", async () => {
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    vi.mocked(api.createChatAgent).mockClear();
    await result.current.sendMessage("hi");
    await waitFor(() => expect(store.getState().chat.isRunning).toBe(false));
    const messages = store.getState().chat.messages;
    expect(messages.some((m) => m.role === "user" && m.content === "hi")).toBe(true);
    expect(api.createChatAgent).toHaveBeenCalledWith("sess-abc");
    expect(mockAgent.runAgent).toHaveBeenCalled();
  });

  it("sendMessage dispatches setError when runAgent throws", async () => {
    mockAgent.runAgent.mockRejectedValueOnce(new Error("stream failure"));
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    await result.current.sendMessage("hi");
    await waitFor(() => expect(store.getState().chat.error).not.toBeNull());
  });

  it("init effect skips fetch when initialSessionId is null (/sessions/new route)", async () => {
    const store = makeStore();
    renderHook(() => useChat(null), { wrapper: makeWrapper(store) });
    // give the effect a tick — should not fetch and should not set sessionId
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getSessionMessages).not.toHaveBeenCalled();
    expect(store.getState().chat.sessionId).toBeNull();
  });

  it("init effect clears leftover sessionId and messages when entering /sessions/new", async () => {
    const store = makeStore({
      chat: {
        messages: [{ id: "stale", role: "user", content: "previous" }],
        sessionId: "sess-prev",
        isRunning: false,
        isStreaming: false,
        error: null,
        pendingRenderCalls: [],
      },
    });
    renderHook(() => useChat(null), { wrapper: makeWrapper(store) });
    await new Promise((r) => setTimeout(r, 0));
    expect(store.getState().chat.sessionId).toBeNull();
    expect(store.getState().chat.messages).toEqual([]);
  });

  it("init effect skips fetch when Redux sessionId already matches initialSessionId", async () => {
    const store = makeStore({
      chat: {
        messages: [],
        sessionId: "sess-abc",
        isRunning: false,
        isStreaming: false,
        error: null,
        pendingRenderCalls: [],
      },
    });
    renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getSessionMessages).not.toHaveBeenCalled();
  });

  it("returns pendingRenderCalls mirroring the store", () => {
    const store = makeStore({
      chat: {
        messages: [],
        sessionId: "sess-abc",
        isRunning: false,
        isStreaming: false,
        error: null,
        pendingRenderCalls: [{ toolCallId: "tc-1", surfaceId: "s1" }],
      },
    });
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    expect(result.current.pendingRenderCalls).toEqual([{ toolCallId: "tc-1", surfaceId: "s1" }]);
  });

  it("sendMessage on /sessions/new generates uuid, sets sessionId, replaces URL, runs agent", async () => {
    const { useRouter } = await import("next/navigation");
    const replaceMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push: vi.fn(), replace: replaceMock } as never);
    const uuidSpy = vi.spyOn(crypto, "randomUUID");
    uuidSpy.mockReturnValueOnce("00000000-0000-4000-8000-000000000001"); // session uuid
    uuidSpy.mockReturnValueOnce("00000000-0000-4000-8000-000000000002"); // message uuid
    const store = makeStore();
    const { result } = renderHook(() => useChat(null), { wrapper: makeWrapper(store) });
    await new Promise((r) => setTimeout(r, 0));
    await result.current.sendMessage("hello");
    expect(replaceMock).toHaveBeenCalledWith("/sessions/00000000-0000-4000-8000-000000000001");
    expect(store.getState().chat.sessionId).toBe("00000000-0000-4000-8000-000000000001");
    expect(api.createChatAgent).toHaveBeenCalledWith("00000000-0000-4000-8000-000000000001");
    expect(mockAgent.runAgent).toHaveBeenCalled();
    uuidSpy.mockRestore();
  });

  it("preserves a pending render_a2ui ack across a /sessions/new remount", async () => {
    let capturedSubscriber: AgentSubscriber | undefined;
    let resolveRunAgent: () => void = () => {};
    mockAgent.runAgent.mockImplementationOnce((_opts: unknown, subscriber: AgentSubscriber) => {
      capturedSubscriber = subscriber;
      // Stays pending until resolveRunAgent() is called below — mirrors the
      // still-streaming run whose promise chain the OLD <Chat>/useChat instance
      // holds a closure over even after router.replace remounts the component.
      return new Promise<void>((resolve) => {
        resolveRunAgent = resolve;
      });
    });

    const store = makeStore();
    const { result: result1, unmount } = renderHook(() => useChat(null), {
      wrapper: makeWrapper(store),
    });
    await new Promise((r) => setTimeout(r, 0));

    act(() => {
      void result1.current.sendMessage("hello");
    });
    const sessionId = store.getState().chat.sessionId;
    expect(sessionId).not.toBeNull();

    await act(async () => {
      await capturedSubscriber?.onToolCallEndEvent?.({
        event: { toolCallId: "tc-a2ui-1" },
        toolCallName: RENDER_A2UI_TOOL_NAME,
        toolCallArgs: { surfaceId: "s1" },
      } as unknown as Parameters<NonNullable<AgentSubscriber["onToolCallEndEvent"]>>[0]);
    });
    expect(store.getState().chat.pendingRenderCalls).toEqual([
      { toolCallId: "tc-a2ui-1", surfaceId: "s1" },
    ]);

    // The stream finishes (dispatch(finishRun()) runs on the OLD mount's closure,
    // but writes into the same shared store) before the user gets to click the
    // surface button.
    resolveRunAgent();
    await waitFor(() => expect(store.getState().chat.isRunning).toBe(false));

    // Simulate the remount: the old <Chat>/useChat instance is torn down and a
    // fresh instance mounts for the now-URL'd session.
    unmount();
    mockAgent.addMessage.mockClear();

    const { result: result2 } = renderHook(() => useChat(sessionId), {
      wrapper: makeWrapper(store),
    });
    await new Promise((r) => setTimeout(r, 0));

    await result2.current.sendA2uiAction({
      name: "click",
      surfaceId: "s1",
      sourceComponentId: "btn1",
      context: {},
    });

    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "tool", toolCallId: "tc-a2ui-1" })
    );
    expect(store.getState().chat.pendingRenderCalls).toEqual([]);
  });
});
