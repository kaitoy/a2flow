import { RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import { RENDER_APPROVAL_TOOL_NAME } from "@/lib/approvalTool";

/**
 * Activity-message type used to render a tool-call status line (running/done)
 * from a backend function call. Distinct from the A2UI and approval activity
 * types so the message list can dispatch to the dedicated tool-activity component.
 */
export const TOOL_CALL_ACTIVITY_TYPE = "tool_call";

/**
 * Activity-message type used to render a streamed reasoning ("thinking") panel
 * from the agent's `REASONING_*` events.
 */
export const REASONING_ACTIVITY_TYPE = "reasoning";

/**
 * Name of the backend proxy tool through which the agent invokes any MCP tool
 * bound to the in-progress workflow task. The human-meaningful tool name is
 * carried in its `tool_name` argument, so a `call_mcp_tool` call represents a
 * user-added MCP tool invocation rather than an internal A2Flow operation.
 */
export const CALL_MCP_TOOL_NAME = "call_mcp_tool";

/** Lifecycle state of a tool-call activity line. */
export type ToolCallStatus = "running" | "done";

/**
 * Content stored on a {@link TOOL_CALL_ACTIVITY_TYPE} activity message, driving
 * {@link ToolActivityBubble}.
 */
export interface ToolCallActivityContent {
  /** Display name of the tool (the real MCP tool name for `call_mcp_tool`). */
  name: string;
  /** Whether the line is still running or has completed. */
  status: ToolCallStatus;
  /** True when this line represents a user-added MCP tool call. */
  isMcp?: boolean;
}

/**
 * Content stored on a {@link REASONING_ACTIVITY_TYPE} activity message, driving
 * {@link ReasoningBubble}.
 */
export interface ReasoningActivityContent {
  /** The accumulated reasoning text streamed so far. */
  text: string;
}

/**
 * Resolve the user-facing display name for a tool call. For the `call_mcp_tool`
 * proxy the meaningful name lives in the `tool_name` argument; every other tool
 * is shown under its own function name.
 *
 * @param toolCallName - The function name from the AG-UI tool-call event.
 * @param args - The parsed tool-call arguments, when available.
 * @returns The name to display in the chat.
 */
export function getToolDisplayName(
  toolCallName: string,
  args?: Record<string, unknown> | null
): string {
  if (toolCallName === CALL_MCP_TOOL_NAME) {
    const toolName = args?.tool_name;
    if (typeof toolName === "string" && toolName) return toolName;
  }
  return toolCallName;
}

/**
 * Whether a tool call should be hidden from the generic tool-activity stream
 * because it already has its own dedicated UI (A2UI surfaces, approval controls).
 *
 * @param toolCallName - The function name from the AG-UI tool-call event.
 * @returns True when the tool is rendered by a dedicated component instead.
 */
export function isHiddenToolName(toolCallName: string): boolean {
  return toolCallName === RENDER_A2UI_TOOL_NAME || toolCallName === RENDER_APPROVAL_TOOL_NAME;
}
