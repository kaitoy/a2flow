import { A2UI_OPERATIONS_KEY, A2UIActivityType } from "@ag-ui/a2ui-middleware";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { formatActionContent, RENDER_ACK_CONTENT } from "@/lib/a2uiAction";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  REASONING_ACTIVITY_TYPE,
  TOOL_CALL_ACTIVITY_TYPE,
} from "@/lib/agentActivity";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
import { ActivityMessageBubble } from "./ActivityMessageBubble";

vi.mock("./A2uiRenderer", () => ({
  A2uiRenderer: ({
    onAction,
    resolved,
    payload,
  }: {
    onAction?: unknown;
    resolved?: boolean;
    payload?: unknown;
  }) => (
    <div
      data-testid="a2ui-renderer-mock"
      data-has-action={String(!!onAction)}
      data-resolved={String(!!resolved)}
      data-payload={JSON.stringify(payload)}
    />
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

  it("renders the avatar beside an A2UI surface when provided", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { a2ui_operations: [] },
        }}
        avatar={<div data-testid="mock-avatar" />}
      />
    );
    expect(screen.getByTestId("mock-avatar")).toBeInTheDocument();
  });

  it("ignores the avatar for the tool_call activity type", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "tc-1",
          role: "activity",
          activityType: TOOL_CALL_ACTIVITY_TYPE,
          content: { name: "search_web", status: "done" },
        }}
        avatar={<div data-testid="mock-avatar" />}
      />
    );
    expect(screen.queryByTestId("mock-avatar")).not.toBeInTheDocument();
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

  it("renders the avatar beside the approval controls when provided", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "tc-1",
          role: "activity",
          activityType: APPROVAL_ACTIVITY_TYPE,
          content: { approvalId: "appr-1", title: "Deploy?" },
        }}
        avatar={<div data-testid="mock-avatar" />}
      />
    );
    expect(screen.getByTestId("approval-controls-mock")).toBeInTheDocument();
    expect(screen.getByTestId("mock-avatar")).toBeInTheDocument();
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

  it("forwards isThinking to the reasoning bubble's live edge", () => {
    const { container } = render(
      <ActivityMessageBubble
        message={{
          id: "r-1",
          role: "activity",
          activityType: REASONING_ACTIVITY_TYPE,
          content: { text: "Let me think about this." },
        }}
        isThinking={true}
      />
    );
    expect(container.querySelector(".live-edge")).toBeInTheDocument();
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

  it("renders an A2UI surface as interactive when its render call is pending", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_OPERATIONS_KEY]: [], [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        }}
        onAction={vi.fn()}
        pendingToolCallIds={new Set(["tc-1"])}
      />
    );
    const el = screen.getByTestId("a2ui-renderer-mock");
    expect(el).toHaveAttribute("data-resolved", "false");
    expect(el).toHaveAttribute("data-has-action", "true");
  });

  it("renders an A2UI surface as resolved when its render call is absent from pendingToolCallIds", () => {
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_OPERATIONS_KEY]: [], [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        }}
        onAction={vi.fn()}
        pendingToolCallIds={new Set()}
      />
    );
    const el = screen.getByTestId("a2ui-renderer-mock");
    expect(el).toHaveAttribute("data-resolved", "true");
    expect(el).toHaveAttribute("data-has-action", "false");
  });

  it("pre-fills a resolved surface with the data model the user submitted", () => {
    const payload = [
      { version: "v0.9", createSurface: { surfaceId: "s1" } },
      { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { plan: [] } } },
    ];
    // The submitted data model carries every input the user made — not just the
    // `context` bindings the agent happened to declare on the button.
    const content = formatActionContent(
      { name: "confirm", surfaceId: "s1", sourceComponentId: "btn", context: {} },
      { userName: "Alice", plan: ["pro"] }
    );
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_OPERATIONS_KEY]: payload, [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        }}
        pendingToolCallIds={new Set()}
        toolResultContentByCallId={new Map([["tc-1", content]])}
      />
    );
    const rendered = JSON.parse(
      screen.getByTestId("a2ui-renderer-mock").getAttribute("data-payload") ?? "null"
    );
    expect(rendered).toEqual([
      payload[0],
      {
        version: "v0.9",
        updateDataModel: { surfaceId: "s1", value: { userName: "Alice", plan: ["pro"] } },
      },
    ]);
  });

  it("pre-fills from a legacy prose tool result wrapped by ag-ui-adk", () => {
    const payload = [{ version: "v0.9", createSurface: { surfaceId: "s1" } }];
    // How a session written before the JSON format reads back after a reload.
    const content = JSON.stringify({
      success: true,
      result:
        'User performed action "confirm" on surface "s1" (component: btn). Context: {"userName":"Alice"}',
      status: "completed",
    });
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_OPERATIONS_KEY]: payload, [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        }}
        pendingToolCallIds={new Set()}
        toolResultContentByCallId={new Map([["tc-1", content]])}
      />
    );
    const rendered = JSON.parse(
      screen.getByTestId("a2ui-renderer-mock").getAttribute("data-payload") ?? "null"
    );
    expect(rendered).toEqual([
      ...payload,
      { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { userName: "Alice" } } },
    ]);
  });

  it("does not augment the payload when the resolving tool result is just the no-op ack", () => {
    const payload = [{ version: "v0.9", createSurface: { surfaceId: "s1" } }];
    render(
      <ActivityMessageBubble
        message={{
          id: "1",
          role: "activity",
          activityType: A2UIActivityType,
          content: { [A2UI_OPERATIONS_KEY]: payload, [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-1" },
        }}
        pendingToolCallIds={new Set()}
        toolResultContentByCallId={new Map([["tc-1", RENDER_ACK_CONTENT]])}
      />
    );
    const rendered = JSON.parse(
      screen.getByTestId("a2ui-renderer-mock").getAttribute("data-payload") ?? "null"
    );
    expect(rendered).toEqual(payload);
  });
});
