import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { startRun } from "@/store/chatSlice";
import { makeStore } from "@/test/test-utils";
import { useChat } from "./useChat";

vi.mock("@/lib/api", () => ({
  createChatAgent: vi.fn(),
  createSession: vi.fn(),
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
  // Wait for getSessionMessages to resolve so resumeSession has been dispatched
  await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalled());
  await waitFor(() => expect(store.getState().chat.sessionId).toBe("sess-abc"));
}

beforeEach(() => {
  vi.mocked(api.createChatAgent).mockReturnValue(mockAgent as never);
  vi.mocked(api.getSessionMessages).mockResolvedValue([]);
  vi.mocked(api.createSession).mockResolvedValue("new-session-id");
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

  it("newSession calls createSession and router.push", async () => {
    const { useRouter } = await import("next/navigation");
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push: pushMock } as never);
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    await result.current.newSession();
    expect(api.createSession).toHaveBeenCalledWith("user");
    expect(pushMock).toHaveBeenCalledWith("/sessions/new-session-id");
  });

  it("newSession dispatches setError when createSession fails", async () => {
    vi.mocked(api.createSession).mockRejectedValueOnce(new Error("network error"));
    const store = makeStore();
    const { result } = renderHook(() => useChat("sess-abc"), { wrapper: makeWrapper(store) });
    await waitForInit(store);
    await result.current.newSession();
    await waitFor(() => expect(store.getState().chat.error).not.toBeNull());
  });
});
