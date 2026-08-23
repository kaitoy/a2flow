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

  it("moves another participant's message to the left with the avatar leading", () => {
    const { container } = render(
      <UserMessageBubble
        message={{ id: "1", role: "user", content: "hello" }}
        avatar={<span data-testid="sender-avatar">A</span>}
        isOwn={false}
      />
    );
    const row = container.firstChild as HTMLElement;
    expect(row).toHaveClass("justify-start");
    expect(row).not.toHaveClass("justify-end");
    // The avatar sits on the outer (left) edge, before the bubble.
    expect(row.firstChild).toBe(screen.getByTestId("sender-avatar"));
  });

  it("tints another participant's bubble apart from the agent's glass panel", () => {
    render(
      <UserMessageBubble
        message={{ id: "1", role: "user", content: "hello" }}
        avatar={<span data-testid="sender-avatar">A</span>}
        isOwn={false}
      />
    );
    const bubble = screen.getByText("hello");
    expect(bubble).toHaveClass("bg-secondary/12");
    expect(bubble).toHaveClass("border-secondary/25");
    expect(bubble).not.toHaveClass("bg-gradient-to-br");
  });

  it("keeps the viewer's own message right-aligned with the avatar trailing", () => {
    const { container } = render(
      <UserMessageBubble
        message={{ id: "1", role: "user", content: "hello" }}
        avatar={<span data-testid="sender-avatar">A</span>}
        isOwn
      />
    );
    const row = container.firstChild as HTMLElement;
    expect(row).toHaveClass("justify-end");
    expect(row.lastChild).toBe(screen.getByTestId("sender-avatar"));
    expect(screen.getByText("hello")).toHaveClass("bg-gradient-to-br");
  });

  it("stays right-aligned without an avatar even when it is not the viewer's own", () => {
    // The single-user chat passes no avatar and no ownership; a lone sender's
    // messages belong on their own side regardless.
    const { container } = render(
      <UserMessageBubble message={{ id: "1", role: "user", content: "hello" }} isOwn={false} />
    );
    expect(container.firstChild).toHaveClass("justify-end");
    expect(screen.getByText("hello")).toHaveClass("bg-gradient-to-br");
  });
});
