import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { makeStore } from "@/test/test-utils";
import { useWorkflowSessionChat } from "./useWorkflowSessionChat";

vi.mock("@/lib/api", () => ({
  createWorkflowSessionAgent: vi.fn(),
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

beforeEach(() => {
  vi.mocked(api.createWorkflowSessionAgent).mockClear();
  vi.mocked(api.createWorkflowSessionAgent).mockReturnValue(mockAgent as never);
  vi.mocked(api.getSessionMessages).mockResolvedValue([]);
  mockAgent.addMessage.mockClear();
  mockAgent.runAgent.mockClear();
});

describe("useWorkflowSessionChat", () => {
  it("calls getSessionMessages on mount with the given sessionId", async () => {
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalledWith("sess-abc"));
  });

  it("auto-sends workflowPrompt when messages are empty on mount", async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() =>
      expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("ws-1", "sess-abc")
    );
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    const messages = store.getState().chat.messages;
    expect(messages.some((m) => m.role === "user" && m.content === "Do the thing")).toBe(true);
  });

  it("does NOT auto-send when messages already exist", async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "previous message" },
    ]);
    const store = makeStore();
    renderHook(() => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"), {
      wrapper: makeWrapper(store),
    });
    await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalled());
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    expect(api.createWorkflowSessionAgent).not.toHaveBeenCalled();
  });

  it("sendMessage uses createWorkflowSessionAgent with the correct ids", async () => {
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(api.getSessionMessages).toHaveBeenCalled());
    // Wait for auto-send to finish
    await waitFor(() => expect(mockAgent.runAgent).toHaveBeenCalled());
    mockAgent.runAgent.mockClear();
    vi.mocked(api.createWorkflowSessionAgent).mockClear();

    await result.current.sendMessage("hello");
    expect(api.createWorkflowSessionAgent).toHaveBeenCalledWith("ws-1", "sess-abc");
    expect(mockAgent.runAgent).toHaveBeenCalled();
  });

  it("sendApprovalResult posts the decision as a tool result and resumes the run", async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    mockAgent.addMessage.mockClear();
    mockAgent.runAgent.mockClear();

    await result.current.sendApprovalResult("tool-call-1", "approved");

    expect(mockAgent.addMessage).toHaveBeenCalledWith(
      expect.objectContaining({ role: "tool", toolCallId: "tool-call-1", content: "approved" })
    );
    expect(mockAgent.runAgent).toHaveBeenCalled();
  });

  it("dispatches setError when runAgent throws during sendMessage", async () => {
    vi.mocked(api.getSessionMessages).mockResolvedValue([
      { id: "m1", role: "user", content: "existing" },
    ]);
    mockAgent.runAgent.mockRejectedValueOnce(new Error("stream failure"));
    const store = makeStore();
    const { result } = renderHook(
      () => useWorkflowSessionChat("ws-1", "sess-abc", "Do the thing"),
      { wrapper: makeWrapper(store) }
    );
    await waitFor(() => expect(store.getState().chat.messages).toHaveLength(1));
    await result.current.sendMessage("hi");
    await waitFor(() => expect(store.getState().chat.error).not.toBeNull());
  });
});
