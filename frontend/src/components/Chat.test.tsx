import { screen } from "@testing-library/react";
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
    pendingRenderCalls: [{ toolCallId: "tc-1", surfaceId: "s1" }],
    sendMessage: vi.fn(),
    sendA2uiAction: vi.fn(),
  })),
}));

vi.mock("./MessageList", () => ({
  MessageList: ({ pendingRenderCalls }: { pendingRenderCalls?: unknown[] }) => (
    <div data-testid="message-list-mock" data-pending-count={pendingRenderCalls?.length ?? 0} />
  ),
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
  it("renders MessageList and ChatInput", () => {
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByTestId("message-list-mock")).toBeInTheDocument();
    expect(screen.getByTestId("chat-input-mock")).toBeInTheDocument();
  });

  it("forwards pendingRenderCalls to MessageList", () => {
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByTestId("message-list-mock")).toHaveAttribute("data-pending-count", "1");
  });

  it("ChatInput disabled prop reflects isRunning", () => {
    vi.mocked(useChat).mockReturnValueOnce({
      messages: [],
      sessionId: "sess-1",
      isRunning: true,
      isStreaming: false,
      error: null,
      pendingRenderCalls: [],
      sendMessage: vi.fn(),
      sendA2uiAction: vi.fn(),
    });
    render(<Chat sessionId="sess-1" />);
    expect(screen.getByTestId("chat-input-mock")).toBeDisabled();
  });
});
