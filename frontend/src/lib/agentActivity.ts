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

/**
 * Content key holding the `render_a2ui` tool call id that produced an A2UI
 * activity message, stamped on at construction time (both the live-streaming
 * and resumed-history paths) so the UI can look up who resolved that call
 * without parsing it back out of the message's own id, whose format differs
 * between the two paths.
 */
export const A2UI_SOURCE_TOOL_CALL_ID_KEY = "sourceToolCallId";

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
  /**
   * The arguments the call was made with, unwrapped for `call_mcp_tool` so the
   * target tool's own arguments show rather than the proxy's envelope. Absent
   * while the call is still streaming its arguments.
   */
  args?: unknown;
  /** The parsed tool result, once it has come back. */
  result?: unknown;
  /**
   * True when the result came from a tool mock rather than the real tool (see
   * the backend's `infrastructure.tool_mocks`), so nothing actually happened.
   */
  mocked?: boolean;
}

/**
 * Unwrap the arguments worth showing for a tool call.
 *
 * `call_mcp_tool` is a proxy: its own arguments are `{server_id, tool_name,
 * arguments}`, and the first two are already what the line is labelled with, so
 * the nested `arguments` object is what the reader actually wants. Every other
 * tool shows its arguments as they are.
 *
 * @param toolCallName - The function name from the AG-UI tool-call event.
 * @param args - The parsed tool-call arguments.
 * @returns The arguments to display.
 */
export function getToolCallArguments(toolCallName: string, args: Record<string, unknown>): unknown {
  if (toolCallName === CALL_MCP_TOOL_NAME) {
    const inner = args.arguments;
    if (inner !== null && typeof inner === "object") return inner;
  }
  return args;
}

/**
 * Parse a tool result payload, which arrives as a JSON string on the wire.
 *
 * A result that is not JSON (a plain-text tool answer, or a truncated stream) is
 * returned as the original string rather than dropped — showing the raw text is
 * more useful than showing nothing.
 *
 * @param raw - The `content` of an AG-UI `TOOL_CALL_RESULT` event, or of a
 *   persisted `tool` message.
 * @returns The parsed value, or the original string when it is not JSON.
 */
export function parseToolResult(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/**
 * Whether a parsed tool result was produced by a mock instead of the real tool.
 *
 * The backend marks every stubbed result with `"mocked": true` (see
 * `infrastructure/tool_mocks.py`), which is the only signal the client gets —
 * and the only one it needs, since a mocked call is otherwise shaped exactly
 * like a real one.
 *
 * @param result - The parsed tool result.
 * @returns True when the result is a stub.
 */
export function isMockedResult(result: unknown): boolean {
  return (
    result !== null &&
    typeof result === "object" &&
    (result as Record<string, unknown>).mocked === true
  );
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
