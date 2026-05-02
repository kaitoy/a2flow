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
            { type: "image_url", image_url: { url: "http://example.com/img.png" } },
          ],
        }}
      />
    );
    expect(screen.getByText("hi")).toBeInTheDocument();
  });
});
