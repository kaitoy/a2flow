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
    await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalledWith("sess-abc", "user"));
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

  it("switchSession calls router.push when not running", async () => {
    const { useRouter } = await import("next/navigation");
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push: pushMock } as never);
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    result.current.switchSession("sess-xyz");
    expect(pushMock).toHaveBeenCalledWith("/sessions/sess-xyz");
  });

  it("switchSession does NOT call router.push when isRunning", async () => {
    const { useRouter } = await import("next/navigation");
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push: pushMock } as never);
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    act(() => {
      store.dispatch(startRun());
    });
    result.current.switchSession("sess-xyz");
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("newSession navigates to /newSession (no backend call)", async () => {
    const { useRouter } = await import("next/navigation");
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push: pushMock } as never);
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    result.current.newSession();
    expect(pushMock).toHaveBeenCalledWith("/newSession");
  });

  it("init effect skips fetch when initialSessionId is null (/newSession route)", async () => {
    const store = makeStore();
    renderHook(() => useChat(null), { wrapper: makeWrapper(store) });
    // give the effect a tick — should not fetch and should not set sessionId
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getSessionMessages).not.toHaveBeenCalled();
    expect(store.getState().chat.sessionId).toBeNull();
  });

  it("init effect clears leftover sessionId and messages when entering /newSession", async () => {
    const store = makeStore({
      chat: {
        messages: [{ id: "stale", role: "user", content: "previous" }],
        sessionId: "sess-prev",
        userId: "user",
        isRunning: false,
        isStreaming: false,
        error: null,
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
        userId: "user",
        isRunning: false,
        isStreaming: false,
        error: null,
      },
    });
    renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getSessionMessages).not.toHaveBeenCalled();
  });

  it("sendMessage on /newSession generates uuid, sets sessionId, replaces URL, runs agent", async () => {
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
});
