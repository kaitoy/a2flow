import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render } from "@/test/test-utils";
import { Chat } from "./Chat";

vi.mock("@/hooks/useChat", () => ({
  useChat: vi.fn(() => ({
    messages: [],
    sessionId: "sess-1",
    isRunning: false,
    isStreaming: false,
    error: null,
    sendMessage: vi.fn(),
    sendA2uiAction: vi.fn(),
    switchSession: vi.fn(),
    newSession: vi.fn(),
  })),
}));

vi.mock("./SessionList", () => ({
  SessionList: () => <div data-testid="session-list-mock" />,
}));

vi.mock("./MessageList", () => ({
  MessageList: () => <div data-testid="message-list-mock" />,
}));

vi.mock("./ChatInput", () => ({
  ChatInput: ({ onSend, disabled }: { onSend: (m: string) => void; disabled: boolean }) => (
    <button
      type="button"
      data-testid="chat-input-mock"
      disabled={disabled}
      onClick={() => onSend("test")}
    >
      Send
    </button>
  ),
}));

import { useChat } from "@/hooks/useChat";

describe("Chat", () => {
  it("renders SessionList, MessageList, and ChatInput", () => {
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByTestId("session-list-mock")).toBeInTheDocument();
    expect(screen.getByTestId("message-list-mock")).toBeInTheDocument();
    expect(screen.getByTestId("chat-input-mock")).toBeInTheDocument();
  });

  it("shows error banner when error is set", () => {
    vi.mocked(useChat).mockReturnValueOnce({
      messages: [],
      sessionId: "sess-1",
      isRunning: false,
      isStreaming: false,
      error: "Something went wrong",
      sendMessage: vi.fn(),
      sendA2uiAction: vi.fn(),
      switchSession: vi.fn(),
      newSession: vi.fn(),
    });
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("does not show error banner when error is null", () => {
    render(<Chat sessionId="sess-1" />);
    expect(screen.queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });

  it("clicking dismiss button dispatches clearError to the store", async () => {
    vi.mocked(useChat).mockReturnValue({
      messages: [],
      sessionId: "sess-1",
      isRunning: false,
      isStreaming: false,
      error: "Oops",
      sendMessage: vi.fn(),
      sendA2uiAction: vi.fn(),
      switchSession: vi.fn(),
      newSession: vi.fn(),
    });
    const { store } = render(<Chat sessionId="sess-1" />, {
      preloadedState: {
        chat: {
          messages: [],
          sessionId: "sess-1",
          userId: "user",
          isRunning: false,
          isStreaming: false,
          error: "Oops",
        },
      },
    });
    await userEvent.click(screen.getByLabelText("Dismiss error"));
    expect(store.getState().chat.error).toBeNull();
  });

  it("ChatInput disabled prop reflects isRunning", () => {
    vi.mocked(useChat).mockReturnValueOnce({
      messages: [],
      sessionId: "sess-1",
      isRunning: true,
      isStreaming: false,
      error: null,
      sendMessage: vi.fn(),
      sendA2uiAction: vi.fn(),
      switchSession: vi.fn(),
      newSession: vi.fn(),
    });
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByTestId("chat-input-mock")).toBeDisabled();
  });
});
