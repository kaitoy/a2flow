import { A2UIActivityType, RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import type { AgentSubscriber } from "@ag-ui/client";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  CALL_MCP_TOOL_NAME,
  getToolDisplayName,
  isHiddenToolName,
  REASONING_ACTIVITY_TYPE,
  TOOL_CALL_ACTIVITY_TYPE,
} from "@/lib/agentActivity";
import { logAgUiEvent } from "@/lib/devEventLogger";
import type { AppDispatch } from "@/store";
import {
  addActivityMessage,
  appendDelta,
  endAssistantMessage,
  setError,
  startAssistantMessage,
} from "@/store/chatSlice";

/**
 * Prefix the A2UI middleware uses for the stable `messageId` it assigns an
 * A2UI surface's activity snapshots (verified in
 * `@ag-ui/a2ui-middleware`'s bundled source): `a2ui-surface-${toolCallId}`.
 */
const A2UI_SURFACE_MESSAGE_ID_PREFIX = "a2ui-surface-";

/** Options that tailor the subscriber to a particular chat surface. */
export interface AgentSubscriberOptions {
  /**
   * Called whenever a RENDER_A2UI tool call ends, with the tool call ID and its
   * parsed arguments (carrying the rendered `surfaceId`), so the next agent run
   * can acknowledge the render as a tool result — and a user action on that
   * surface can be delivered as this specific call's result.
   */
  onRenderA2uiEnd: (toolCallId: string, args: Record<string, unknown>) => void;
  /**
   * Optional handler invoked when a `render_approval` tool call ends, receiving
   * the tool call ID and its parsed arguments. Only the workflow chat surface
   * renders approval controls.
   */
  onRenderApprovalEnd?: (toolCallId: string, args: Record<string, unknown>) => void;
}

/**
 * Build the AG-UI subscriber object that maps incoming events to Redux actions.
 *
 * Beyond the assistant-text and A2UI/approval handling, this surfaces the
 * agent's intermediate work in the chat stream: each non-rendering tool call
 * becomes a {@link TOOL_CALL_ACTIVITY_TYPE} activity line that transitions from
 * `running` to `done`, and streamed `REASONING_*` events accumulate into a
 * {@link REASONING_ACTIVITY_TYPE} "thinking" panel.
 *
 * @param dispatch - The Redux dispatch used to apply the mapped actions.
 * @param options - Per-surface callbacks (see {@link AgentSubscriberOptions}).
 * @returns The {@link AgentSubscriber} to pass to `agent.runAgent`.
 */
export function createAgentSubscriber(
  dispatch: AppDispatch,
  options: AgentSubscriberOptions
): AgentSubscriber {
  return {
    onEvent: async ({ event }) => {
      logAgUiEvent(event);
    },
    onTextMessageStartEvent: async ({ event }) => {
      dispatch(startAssistantMessage(event.messageId));
    },
    onTextMessageContentEvent: async ({ event }) => {
      dispatch(appendDelta({ messageId: event.messageId, delta: event.delta }));
    },
    onTextMessageEndEvent: async ({ event: _event }) => {
      dispatch(endAssistantMessage());
    },
    onActivitySnapshotEvent: async ({ event }) => {
      const content = event.content as Record<string, unknown>;
      // Stamp the render call's toolCallId onto A2UI surface snapshots (see
      // A2UI_SOURCE_TOOL_CALL_ID_KEY) by stripping the middleware's known
      // messageId prefix, so the UI can look up who resolved this call
      // without re-parsing this id format elsewhere.
      const stampedContent =
        event.activityType === A2UIActivityType &&
        event.messageId.startsWith(A2UI_SURFACE_MESSAGE_ID_PREFIX)
          ? {
              ...content,
              [A2UI_SOURCE_TOOL_CALL_ID_KEY]: event.messageId.slice(
                A2UI_SURFACE_MESSAGE_ID_PREFIX.length
              ),
            }
          : content;
      dispatch(
        addActivityMessage({
          id: event.messageId,
          activityType: event.activityType,
          content: stampedContent,
        })
      );
    },
    onToolCallStartEvent: async ({ event }) => {
      if (isHiddenToolName(event.toolCallName)) return;
      dispatch(
        addActivityMessage({
          id: event.toolCallId,
          activityType: TOOL_CALL_ACTIVITY_TYPE,
          content: { name: getToolDisplayName(event.toolCallName), status: "running" },
        })
      );
    },
    onToolCallEndEvent: async ({ event, toolCallName, toolCallArgs }) => {
      if (toolCallName === RENDER_A2UI_TOOL_NAME) {
        options.onRenderA2uiEnd(event.toolCallId, toolCallArgs);
        return;
      }
      if (options.onRenderApprovalEnd && isHiddenToolName(toolCallName)) {
        options.onRenderApprovalEnd(event.toolCallId, toolCallArgs);
        return;
      }
      if (isHiddenToolName(toolCallName)) return;
      dispatch(
        addActivityMessage({
          id: event.toolCallId,
          activityType: TOOL_CALL_ACTIVITY_TYPE,
          content: {
            name: getToolDisplayName(toolCallName, toolCallArgs),
            status: "done",
            isMcp: toolCallName === CALL_MCP_TOOL_NAME,
          },
        })
      );
    },
    onReasoningMessageStartEvent: async ({ event }) => {
      dispatch(
        addActivityMessage({
          id: event.messageId,
          activityType: REASONING_ACTIVITY_TYPE,
          content: { text: "" },
        })
      );
    },
    onReasoningMessageContentEvent: async ({ event, reasoningMessageBuffer }) => {
      dispatch(
        addActivityMessage({
          id: event.messageId,
          activityType: REASONING_ACTIVITY_TYPE,
          content: { text: reasoningMessageBuffer },
        })
      );
    },
    onRunErrorEvent: async ({ event }) => {
      dispatch(setError(event.message));
    },
  };
}
