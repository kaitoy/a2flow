import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatPanelSkeleton } from "./ChatPanelSkeleton";

describe("ChatPanelSkeleton", () => {
  it("renders message-bubble and input-bar skeleton blocks", () => {
    const { container } = render(<ChatPanelSkeleton />);
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
  });

  it("renders no landmark of its own, leaving that to the caller", () => {
    const { container } = render(<ChatPanelSkeleton />);
    expect(container.querySelector('[role="status"]')).toBeNull();
  });
});
