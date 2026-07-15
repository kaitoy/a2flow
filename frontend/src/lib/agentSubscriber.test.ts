import { A2UIActivityType, RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import { describe, expect, it, vi } from "vitest";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  CALL_MCP_TOOL_NAME,
  TOOL_CALL_ACTIVITY_TYPE,
} from "@/lib/agentActivity";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import { RENDER_APPROVAL_TOOL_NAME } from "@/lib/approvalTool";
import { makeStore } from "@/test/test-utils";

function lastActivity(store: ReturnType<typeof makeStore>) {
  const messages = store.getState().chat.messages;
  return messages[messages.length - 1];
}

describe("createAgentSubscriber", () => {
  it("adds a running tool line on tool-call start and marks it done on end", async () => {
    const store = makeStore();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd: vi.fn() });

    await sub.onToolCallStartEvent?.({
      event: { toolCallId: "tc-1", toolCallName: "list_workflow_tasks" },
    } as never);
    let msg = lastActivity(store);
    expect(msg.role).toBe("activity");
    expect((msg.content as { status: string }).status).toBe("running");

    await sub.onToolCallEndEvent?.({
      event: { toolCallId: "tc-1" },
      toolCallName: "list_workflow_tasks",
      toolCallArgs: {},
    } as never);
    msg = lastActivity(store);
    expect(store.getState().chat.messages).toHaveLength(1);
    expect((msg.content as { status: string }).status).toBe("done");
  });

  it("labels a call_mcp_tool end with the real tool name and an MCP flag", async () => {
    const store = makeStore();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd: vi.fn() });

    await sub.onToolCallEndEvent?.({
      event: { toolCallId: "tc-mcp" },
      toolCallName: CALL_MCP_TOOL_NAME,
      toolCallArgs: { tool_name: "search_web" },
    } as never);
    const msg = lastActivity(store);
    if (msg.role !== "activity") throw new Error("expected activity message");
    expect(msg.activityType).toBe(TOOL_CALL_ACTIVITY_TYPE);
    expect(msg.content).toMatchObject({ name: "search_web", status: "done", isMcp: true });
  });

  it("does not create a tool line for render tools", async () => {
    const store = makeStore();
    const onRenderA2uiEnd = vi.fn();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd });

    await sub.onToolCallStartEvent?.({
      event: { toolCallId: "tc-a2ui", toolCallName: RENDER_A2UI_TOOL_NAME },
    } as never);
    expect(store.getState().chat.messages).toHaveLength(0);

    await sub.onToolCallEndEvent?.({
      event: { toolCallId: "tc-a2ui" },
      toolCallName: RENDER_A2UI_TOOL_NAME,
      toolCallArgs: { surfaceId: "surf-1" },
    } as never);
    // The parsed args ride along so the caller can record which surface the
    // pending call rendered.
    expect(onRenderA2uiEnd).toHaveBeenCalledWith("tc-a2ui", { surfaceId: "surf-1" });
    expect(store.getState().chat.messages).toHaveLength(0);
  });

  it("routes render_approval ends to onRenderApprovalEnd without a tool line", async () => {
    const store = makeStore();
    const onRenderApprovalEnd = vi.fn();
    const sub = createAgentSubscriber(store.dispatch, {
      onRenderA2uiEnd: vi.fn(),
      onRenderApprovalEnd,
    });

    await sub.onToolCallEndEvent?.({
      event: { toolCallId: "tc-appr" },
      toolCallName: RENDER_APPROVAL_TOOL_NAME,
      toolCallArgs: { approvalId: "appr-1" },
    } as never);
    expect(onRenderApprovalEnd).toHaveBeenCalledWith("tc-appr", { approvalId: "appr-1" });
    expect(store.getState().chat.messages).toHaveLength(0);
  });

  it("accumulates reasoning content into a reasoning activity", async () => {
    const store = makeStore();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd: vi.fn() });

    await sub.onReasoningMessageStartEvent?.({ event: { messageId: "r-1" } } as never);
    await sub.onReasoningMessageContentEvent?.({
      event: { messageId: "r-1", delta: "Plan" },
      reasoningMessageBuffer: "Plan the steps",
    } as never);

    const msg = lastActivity(store);
    expect(store.getState().chat.messages).toHaveLength(1);
    expect(msg.content).toMatchObject({ text: "Plan the steps" });
  });

  it("stamps sourceToolCallId onto an A2UI activity snapshot from its messageId", async () => {
    const store = makeStore();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd: vi.fn() });

    await sub.onActivitySnapshotEvent?.({
      event: {
        messageId: "a2ui-surface-tc-live-1",
        activityType: A2UIActivityType,
        content: { a2ui_operations: [] },
      },
    } as never);

    const msg = lastActivity(store);
    expect(msg.content).toMatchObject({ [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-live-1" });
  });

  it("leaves non-A2UI activity snapshots untouched", async () => {
    const store = makeStore();
    const sub = createAgentSubscriber(store.dispatch, { onRenderA2uiEnd: vi.fn() });

    await sub.onActivitySnapshotEvent?.({
      event: { messageId: "other-1", activityType: "some_other_type", content: { foo: "bar" } },
    } as never);

    const msg = lastActivity(store);
    expect(msg.content).toEqual({ foo: "bar" });
  });
});
