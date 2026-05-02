import type { Message } from "@ag-ui/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageList } from "./MessageList";

vi.mock("./MessageBubble", () => ({
  MessageBubble: ({ message, isStreaming }: { message: Message; isStreaming: boolean }) => (
    <div data-testid={`bubble-${message.id}`} data-streaming={String(isStreaming)} />
  ),
}));

describe("MessageList", () => {
  it("shows empty state when messages is empty", () => {
    render(<MessageList messages={[]} />);
    expect(screen.getByText("Start a conversation")).toBeInTheDocument();
  });

  it("renders one MessageBubble per message", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "hello" },
    ];
    render(<MessageList messages={messages} />);
    expect(screen.getByTestId("bubble-m1")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-m2")).toBeInTheDocument();
  });

  it("only the last bubble receives isStreaming=true when list isStreaming", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "" },
    ];
    render(<MessageList messages={messages} isStreaming={true} />);
    expect(screen.getByTestId("bubble-m1")).toHaveAttribute("data-streaming", "false");
    expect(screen.getByTestId("bubble-m2")).toHaveAttribute("data-streaming", "true");
  });

  it("calls scrollIntoView on mount", () => {
    render(<MessageList messages={[]} />);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });
});
