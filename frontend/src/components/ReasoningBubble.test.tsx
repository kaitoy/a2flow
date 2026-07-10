import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReasoningBubble } from "./ReasoningBubble";

describe("ReasoningBubble", () => {
  it("renders the reasoning text and a Thinking label", () => {
    render(<ReasoningBubble content={{ text: "First I will plan the steps." }} />);
    expect(screen.getByText("First I will plan the steps.")).toBeInTheDocument();
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });

  it("renders nothing when there is no reasoning text yet", () => {
    const { container } = render(<ReasoningBubble content={{ text: "" }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("carries the live edge while still thinking", () => {
    const { container } = render(
      <ReasoningBubble content={{ text: "Planning the steps." }} isThinking={true} />
    );
    expect(container.querySelector(".live-edge")).toBeInTheDocument();
  });

  it("has no live edge once thinking has stopped", () => {
    const { container } = render(
      <ReasoningBubble content={{ text: "Planning the steps." }} isThinking={false} />
    );
    expect(container.querySelector(".live-edge")).not.toBeInTheDocument();
  });
});
