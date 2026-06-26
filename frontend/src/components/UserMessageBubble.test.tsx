import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UserMessageBubble } from "./UserMessageBubble";

describe("UserMessageBubble", () => {
  it("renders string content with justify-end alignment", () => {
    const { container } = render(
      <UserMessageBubble message={{ id: "1", role: "user", content: "hello" }} />
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("justify-end");
  });

  it("extracts text from InputContent array", () => {
    render(
      <UserMessageBubble
        message={{
          id: "1",
          role: "user",
          content: [{ type: "text", text: "world" }],
        }}
      />
    );
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("ignores non-text InputContent entries", () => {
    render(
      <UserMessageBubble
        message={{
          id: "1",
          role: "user",
          content: [
            { type: "text", text: "hi" },
            { type: "image", source: { type: "url", value: "http://example.com/img.png" } },
          ],
        }}
      />
    );
    expect(screen.getByText("hi")).toBeInTheDocument();
  });

  it("renders the sender avatar beside the bubble when provided", () => {
    const { container } = render(
      <UserMessageBubble
        message={{ id: "1", role: "user", content: "hello" }}
        avatar={<span data-testid="sender-avatar">A</span>}
      />
    );
    expect(screen.getByTestId("sender-avatar")).toBeInTheDocument();
    // The row switches to an avatar-aware layout only when an avatar is present.
    expect(container.firstChild).toHaveClass("items-end");
    expect(container.firstChild).toHaveClass("gap-2");
  });

  it("keeps the plain layout when no avatar is provided", () => {
    const { container } = render(
      <UserMessageBubble message={{ id: "1", role: "user", content: "hello" }} />
    );
    expect(container.firstChild).not.toHaveClass("items-end");
  });
});
