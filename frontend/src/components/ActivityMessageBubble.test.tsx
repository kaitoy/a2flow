import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityMessageBubble } from "./ActivityMessageBubble";

vi.mock("./A2uiRenderer", () => ({
  A2uiRenderer: ({ onAction }: { onAction?: unknown }) => (
    <div data-testid="a2ui-renderer-mock" data-has-action={String(!!onAction)} />
  ),
}));

describe("ActivityMessageBubble", () => {
  it("renders A2uiRenderer for matching activityType", () => {
    render(
      <ActivityMessageBubble
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

  it("renders null for unknown activityType", () => {
    const { container } = render(
      <ActivityMessageBubble
        message={{ id: "1", role: "activity", activityType: "unknown", content: {} }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("forwards onAction to A2uiRenderer", () => {
    const onAction = vi.fn();
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { a2ui_operations: [] },
        }}
        onAction={onAction}
      />
    );
    expect(screen.getByTestId("a2ui-renderer-mock")).toHaveAttribute("data-has-action", "true");
  });
});
