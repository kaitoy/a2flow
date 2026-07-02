import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { REASONING_ACTIVITY_TYPE, TOOL_CALL_ACTIVITY_TYPE } from "@/lib/agentActivity";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
import { ActivityMessageBubble } from "./ActivityMessageBubble";

vi.mock("./A2uiRenderer", () => ({
  A2uiRenderer: ({ onAction }: { onAction?: unknown }) => (
    <div data-testid="a2ui-renderer-mock" data-has-action={String(!!onAction)} />
  ),
}));

vi.mock("./ApprovalControls", () => ({
  ApprovalControls: ({ approvalId }: { approvalId: string }) => (
    <div data-testid="approval-controls-mock" data-approval-id={approvalId} />
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

  it("renders null for an A2UI lifecycle snapshot without operations", () => {
    const { container } = render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { status: "building" },
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
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

  it("renders ApprovalControls for the approval activity type", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "tc-1",
          role: "activity",
          activityType: APPROVAL_ACTIVITY_TYPE,
          content: { approvalId: "appr-1", title: "Deploy?" },
        }}
      />
    );
    expect(screen.getByTestId("approval-controls-mock")).toHaveAttribute(
      "data-approval-id",
      "appr-1"
    );
  });

  it("renders a tool-call status line for the tool_call activity type", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "tc-1",
          role: "activity",
          activityType: TOOL_CALL_ACTIVITY_TYPE,
          content: { name: "search_web", status: "done", isMcp: true },
        }}
      />
    );
    expect(screen.getByText("search_web")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("MCP")).toBeInTheDocument();
  });

  it("renders reasoning text for the reasoning activity type", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "r-1",
          role: "activity",
          activityType: REASONING_ACTIVITY_TYPE,
          content: { text: "Let me think about this." },
        }}
      />
    );
    expect(screen.getByText("Let me think about this.")).toBeInTheDocument();
  });

  it("renders null for an approval activity missing approvalId", () => {
    const { container } = render(
      <ActivityMessageBubble
        message={{
          id: "tc-1",
          role: "activity",
          activityType: APPROVAL_ACTIVITY_TYPE,
          content: {},
        }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
