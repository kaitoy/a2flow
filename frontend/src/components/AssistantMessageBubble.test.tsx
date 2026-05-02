import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssistantMessageBubble } from "./AssistantMessageBubble";

describe("AssistantMessageBubble", () => {
  it("renders text content with justify-start alignment", () => {
    const { container } = render(
      <AssistantMessageBubble message={{ id: "1", role: "assistant", content: "hi there" }} />
    );
    expect(screen.getByText("hi there")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("justify-start");
  });

  it("renders null for empty content when not streaming", () => {
    const { container } = render(
      <AssistantMessageBubble
        message={{ id: "1", role: "assistant", content: "" }}
        isStreaming={false}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders blinking cursor for empty content when streaming", () => {
    const { container } = render(
      <AssistantMessageBubble
        message={{ id: "1", role: "assistant", content: "" }}
        isStreaming={true}
      />
    );
    expect(container).not.toBeEmptyDOMElement();
    expect(container.querySelector(".animate-blink")).toBeInTheDocument();
  });

  it("renders text and blinking cursor when streaming with content", () => {
    const { container } = render(
      <AssistantMessageBubble
        message={{ id: "1", role: "assistant", content: "hello" }}
        isStreaming={true}
      />
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(container.querySelector(".animate-blink")).toBeInTheDocument();
  });
});
