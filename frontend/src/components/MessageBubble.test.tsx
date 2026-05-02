import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "./MessageBubble";

vi.mock("./A2uiRenderer", () => ({
  A2uiRenderer: () => <div data-testid="a2ui-renderer-mock" />,
}));

describe("MessageBubble", () => {
  it("renders user message content with justify-end alignment", () => {
    const { container } = render(
      <MessageBubble message={{ id: "1", role: "user", content: "hello" }} />
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("justify-end");
  });

  it("renders assistant message content with justify-start alignment", () => {
    const { container } = render(
      <MessageBubble message={{ id: "1", role: "assistant", content: "hi there" }} />
    );
    expect(screen.getByText("hi there")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("justify-start");
  });

  it("renders null for empty assistant message when not streaming", () => {
    const { container } = render(
      <MessageBubble message={{ id: "1", role: "assistant", content: "" }} isStreaming={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders blinking cursor for empty assistant message when streaming", () => {
    const { container } = render(
      <MessageBubble message={{ id: "1", role: "assistant", content: "" }} isStreaming={true} />
    );
    expect(container).not.toBeEmptyDOMElement();
    expect(container.querySelector(".animate-blink")).toBeInTheDocument();
  });

  it("renders A2uiRenderer for activity message with A2UIActivityType", () => {
    render(
      <MessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { a2ui_operations: [] },
        }}
      />
    );
    expect(screen.getByTestId("a2ui-renderer-mock")).toBeInTheDocument();
  });

  it("renders null for activity message with unknown activityType", () => {
    const { container } = render(
      <MessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: "unknown_type",
          content: {},
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders null for unknown role", () => {
    const { container } = render(
      <MessageBubble message={{ id: "1", role: "tool" as "user", content: "tool result" }} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
