import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render } from "@/test/test-utils";
import { ChatShell } from "./ChatShell";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("./SessionList", () => ({
  SessionList: ({
    onSelect,
    onNew,
    onDeleted,
    currentSessionId,
    disabled,
  }: {
    onSelect: (id: string) => void;
    onNew: () => void;
    onDeleted?: (id: string) => void;
    currentSessionId: string | null;
    disabled?: boolean;
  }) => (
    <div data-testid="session-list-mock">
      <span data-testid="current-session">{currentSessionId ?? ""}</span>
      <span data-testid="disabled-flag">{disabled ? "yes" : "no"}</span>
      <button type="button" onClick={() => onSelect("sess-xyz")}>
        select
      </button>
      <button type="button" onClick={() => onNew()}>
        new
      </button>
      <button type="button" onClick={() => onDeleted?.("sess-abc")}>
        delete-active
      </button>
      <button type="button" onClick={() => onDeleted?.("sess-other")}>
        delete-other
      </button>
    </div>
  ),
}));

vi.mock("./ThemeToggle", () => ({
  ThemeToggle: () => <div data-testid="theme-toggle-mock" />,
}));

describe("ChatShell", () => {
  it("renders sidebar, logo header, and children", () => {
    render(
      <ChatShell>
        <div data-testid="panel">panel</div>
      </ChatShell>
    );
    expect(screen.getByTestId("session-list-mock")).toBeInTheDocument();
    expect(screen.getByAltText("A2Flow logo")).toBeInTheDocument();
    expect(screen.getByTestId("theme-toggle-mock")).toBeInTheDocument();
    expect(screen.getByTestId("panel")).toBeInTheDocument();
  });

  it("passes current sessionId and isRunning from Redux to SessionList", () => {
    render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: "sess-abc",
            isRunning: true,
            isStreaming: false,
            error: null,
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    expect(screen.getByTestId("current-session")).toHaveTextContent("sess-abc");
    expect(screen.getByTestId("disabled-flag")).toHaveTextContent("yes");
  });

  it("shows error banner when error is set in store", () => {
    render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: null,
            isRunning: false,
            isStreaming: false,
            error: "Something went wrong",
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("does not show error banner when error is null", () => {
    render(
      <ChatShell>
        <div />
      </ChatShell>
    );
    expect(screen.queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });

  it("clicking dismiss button clears the error in the store", async () => {
    const { store } = render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: null,
            isRunning: false,
            isStreaming: false,
            error: "Oops",
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    await userEvent.click(screen.getByLabelText("Dismiss error"));
    expect(store.getState().chat.error).toBeNull();
  });

  it("SessionList onSelect navigates to /sessions/<id>", async () => {
    pushMock.mockClear();
    render(
      <ChatShell>
        <div />
      </ChatShell>
    );
    await userEvent.click(screen.getByRole("button", { name: "select" }));
    expect(pushMock).toHaveBeenCalledWith("/sessions/sess-xyz");
  });

  it("SessionList onNew navigates to /new-session", async () => {
    pushMock.mockClear();
    render(
      <ChatShell>
        <div />
      </ChatShell>
    );
    await userEvent.click(screen.getByRole("button", { name: "new" }));
    expect(pushMock).toHaveBeenCalledWith("/new-session");
  });

  it("onSelect is a no-op while isRunning", async () => {
    pushMock.mockClear();
    render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: "sess-abc",
            isRunning: true,
            isStreaming: false,
            error: null,
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    await userEvent.click(screen.getByRole("button", { name: "select" }));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("onDeleted navigates to /new-session when active session is deleted", async () => {
    pushMock.mockClear();
    render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: "sess-abc",
            isRunning: false,
            isStreaming: false,
            error: null,
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    await userEvent.click(screen.getByRole("button", { name: "delete-active" }));
    expect(pushMock).toHaveBeenCalledWith("/new-session");
  });

  it("onDeleted does not navigate when a non-active session is deleted", async () => {
    pushMock.mockClear();
    render(
      <ChatShell>
        <div />
      </ChatShell>,
      {
        preloadedState: {
          chat: {
            messages: [],
            sessionId: "sess-abc",
            isRunning: false,
            isStreaming: false,
            error: null,
            pendingRenderToolCallIds: [],
          },
        },
      }
    );
    await userEvent.click(screen.getByRole("button", { name: "delete-other" }));
    expect(pushMock).not.toHaveBeenCalled();
  });
});
