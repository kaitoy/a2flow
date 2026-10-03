import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { formatActionContent } from "@/lib/a2uiAction";
import * as api from "@/lib/api";
import { addPendingRenderCall } from "@/store/chatSlice";
import { makeStore } from "@/test/test-utils";
import { useExecutionSessionChat } from "./useExecutionSessionChat";

vi.mock("@/lib/api", () => ({
  createSessionStreamAgent: vi.fn(),
  getExecutionSessionHistory: vi.fn(),
  getUsersByIds: vi.fn(),
  isForbiddenError: vi.fn(),
  listWorkflowTasks: vi.fn(),
  sendSessionInput: vi.fn(),
  uploadSessionFile: vi.fn(),
  SUPPRESS_FORBIDDEN_TOAST: { suppressForbiddenToast: true },
}));

/** A history read returning no messages, the given stream cursor, and no turn under way. */
function history(streamCursor: number, running = false): api.StreamedSessionHistory {
  return { messages: [], senders: new Map(), tasks: new Map(), streamCursor, running };
}

/** A stream agent whose `runAgent` stays open until the test settles it. */
function streamAgent() {
  let finish: () => void = () => {};
  const agent = {
    use: vi.fn(),
    abortRun: vi.fn(),
    runAgent: vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        })
    ),
  };
  return { agent, finish: () => finish() };
}

function makeWrapper(store: ReturnType<typeof makeStore>) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  };
}

function mount(store = makeStore()) {
  return {
    store,
    ...renderHook(() => useExecutionSessionChat("exec-1", "sess-1", "owner-1"), {
      wrapper: makeWrapper(store),
    }),
  };
}

beforeEach(() => {
  vi.mocked(api.getExecutionSessionHistory).mockReset().mockResolvedValue(history(5));
  vi.mocked(api.createSessionStreamAgent)
    .mockReset()
    .mockImplementation(() => streamAgent().agent as never);
  vi.mocked(api.getUsersByIds).mockReset().mockResolvedValue(new Map());
  vi.mocked(api.listWorkflowTasks).mockReset().mockResolvedValue([]);
  vi.mocked(api.isForbiddenError).mockReset().mockReturnValue(false);
  vi.mocked(api.sendSessionInput).mockReset().mockResolvedValue(undefined);
  vi.mocked(api.uploadSessionFile).mockReset();
});

describe("useExecutionSessionChat", () => {
  it("shows the agent working as soon as the history says a turn is queued or running", async () => {
    vi.mocked(api.getExecutionSessionHistory).mockResolvedValue(history(5, true));
    const { result } = mount();
    await waitFor(() => expect(result.current.isRunning).toBe(true));
  });

  it("reads the history, then subscribes to the stream from its cursor", async () => {
    mount();
    await waitFor(() =>
      expect(api.createSessionStreamAgent).toHaveBeenCalledWith("exec-1", "sess-1", 5)
    );
    expect(api.getExecutionSessionHistory).toHaveBeenCalledWith(
      "exec-1",
      "sess-1",
      api.SUPPRESS_FORBIDDEN_TOAST
    );
  });

  it("re-reads the history after a turn and subscribes again from the new cursor", async () => {
    const first = streamAgent();
    vi.mocked(api.createSessionStreamAgent)
      .mockImplementationOnce(() => first.agent as never)
      .mockImplementation(() => streamAgent().agent as never);
    vi.mocked(api.getExecutionSessionHistory)
      .mockResolvedValueOnce(history(5))
      .mockResolvedValue(history(9));
    mount();
    await waitFor(() => expect(first.agent.runAgent).toHaveBeenCalled());

    act(() => first.finish());

    await waitFor(() =>
      expect(api.createSessionStreamAgent).toHaveBeenLastCalledWith("exec-1", "sess-1", 9)
    );
    expect(api.getExecutionSessionHistory).toHaveBeenCalledTimes(2);
  });

  it("stops the stream when unmounted", async () => {
    const stream = streamAgent();
    vi.mocked(api.createSessionStreamAgent).mockImplementation(() => stream.agent as never);
    const { unmount } = mount();
    await waitFor(() => expect(stream.agent.runAgent).toHaveBeenCalled());
    unmount();
    expect(stream.agent.abortRun).toHaveBeenCalled();
  });

  it("queues a message instead of running the agent itself", async () => {
    const { result, store } = mount();
    await waitFor(() => expect(api.createSessionStreamAgent).toHaveBeenCalled());

    await act(async () => {
      await result.current.sendMessage("hello");
    });

    expect(api.sendSessionInput).toHaveBeenCalledWith("exec-1", "sess-1", { message: "hello" });
    const sent = store.getState().chat.messages.filter((m) => m.role === "user");
    expect(sent.map((m) => m.content)).toEqual(["hello"]);
    expect(result.current.locallySentMessageIds.has(sent[0].id)).toBe(true);
  });

  it("uploads attachments first and names them in the message", async () => {
    vi.mocked(api.uploadSessionFile).mockResolvedValue({ name: "data (1).csv" } as never);
    const { result } = mount();
    await waitFor(() => expect(api.createSessionStreamAgent).toHaveBeenCalled());

    await act(async () => {
      await result.current.sendMessage("see attached", [new File(["a"], "data.csv")]);
    });

    expect(api.uploadSessionFile).toHaveBeenCalledWith("exec-1", expect.any(File));
    expect(api.sendSessionInput).toHaveBeenCalledWith("exec-1", "sess-1", {
      message: "see attached\n\nAttached files: data (1).csv",
    });
  });

  it("answers the form the action came from", async () => {
    const { result, store } = mount();
    await waitFor(() => expect(api.createSessionStreamAgent).toHaveBeenCalled());
    act(() => {
      store.dispatch(addPendingRenderCall({ toolCallId: "tc-1", surfaceId: "s1" }));
      store.dispatch(addPendingRenderCall({ toolCallId: "tc-2", surfaceId: "s2" }));
    });
    const action = { name: "submit", surfaceId: "s1", context: {} };

    await act(async () => {
      await result.current.sendA2uiAction(action as never, { region: "eu" });
    });

    expect(api.sendSessionInput).toHaveBeenCalledWith("exec-1", "sess-1", {
      a2uiAction: {
        toolCallId: "tc-1",
        content: formatActionContent(action as never, { region: "eu" }),
      },
    });
  });

  it("reports a FORBIDDEN first read as forbidden and never subscribes", async () => {
    vi.mocked(api.getExecutionSessionHistory).mockRejectedValue(new Error("forbidden"));
    vi.mocked(api.isForbiddenError).mockReturnValue(true);
    const { result } = mount();

    await waitFor(() => expect(result.current.forbidden).toBe(true));
    expect(api.createSessionStreamAgent).not.toHaveBeenCalled();
  });
});
