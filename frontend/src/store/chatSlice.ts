import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PendingRenderCall } from "@/lib/a2uiAction";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  CALL_MCP_TOOL_NAME,
  getToolDisplayName,
  TOOL_CALL_ACTIVITY_TYPE,
} from "@/lib/agentActivity";
import { APPROVAL_ACTIVITY_TYPE, RENDER_APPROVAL_TOOL_NAME } from "@/lib/approvalTool";

export type { Message };

/** Parse a tool call's arguments into a plain object, or return null on failure. */
function parseToolArgs(args: unknown): Record<string, unknown> | null {
  try {
    return JSON.parse(typeof args === "string" ? args : JSON.stringify(args));
  } catch {
    return null;
  }
}

/**
 * Reconstruct an approval activity message from a `render_approval` tool call.
 *
 * Mirrors the live-streaming path (which dispatches an activity message keyed by
 * the tool call id) so resumed sessions show the approve/reject controls again.
 */
function synthesizeApprovalActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>
): Message | null {
  const { approvalId, title, description } = args as {
    approvalId?: string;
    title?: string;
    description?: string;
  };
  if (!approvalId) return null;
  return {
    id: toolCallId,
    role: "activity",
    activityType: APPROVAL_ACTIVITY_TYPE,
    content: { approvalId, title, description },
  } as Message;
}

/** Reconstruct an A2UI activity message from a RENDER_A2UI tool call's args. */
function synthesizeA2UIActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>
): Message | null {
  const { surfaceId, catalogId, components, data } = args as {
    surfaceId?: string;
    catalogId?: string;
    components?: unknown[];
    data?: unknown;
  };
  if (!surfaceId) return null;
  // The message processor resolves catalogId strictly against registered catalog
  // ids. Mirror A2UIMiddleware's live-path behavior: the alias "basic" (or a
  // missing catalogId) maps to the app's registered catalog.
  const resolvedCatalogId = catalogId && catalogId !== "basic" ? catalogId : A2UI_CATALOG_ID;
  const ops: Record<string, unknown>[] = [
    { version: "v0.9", createSurface: { surfaceId, catalogId: resolvedCatalogId } },
    { version: "v0.9", updateComponents: { surfaceId, components: components ?? [] } },
  ];
  if (data != null) ops.push({ version: "v0.9", updateDataModel: { surfaceId, value: data } });
  return {
    // Unique per render call so addActivityMessage's upsert logic (which
    // matches by id) works correctly if the same surface is re-synthesized.
    // Live streaming uses `a2ui-surface-${toolCallId}`; the two never coexist
    // for the same surface because a resume rebuilds the whole message list.
    id: `a2ui-surface-${surfaceId}-${toolCallId}`,
    role: "activity",
    activityType: A2UIActivityType,
    // Stamped alongside the ops so the UI can look up who resolved this
    // render call (see A2UI_SOURCE_TOOL_CALL_ID_KEY) without parsing it back
    // out of the id above, whose format differs from the live-streaming path.
    content: { [A2UI_OPERATIONS_KEY]: ops, [A2UI_SOURCE_TOOL_CALL_ID_KEY]: toolCallId },
  } as Message;
}

/**
 * Reconstruct a completed tool-call activity message from a `call_mcp_tool` call.
 *
 * Only user-added MCP tool calls (always routed through the `call_mcp_tool`
 * proxy) are reproduced on resume; internal A2Flow tool calls are intentionally
 * left out so they stay live-only. The line is shown under the real MCP tool
 * name carried in the call's `tool_name` argument.
 */
function synthesizeMcpToolActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>
): Message {
  return {
    id: toolCallId,
    role: "activity",
    activityType: TOOL_CALL_ACTIVITY_TYPE,
    content: { name: getToolDisplayName(CALL_MCP_TOOL_NAME, args), status: "done", isMcp: true },
  } as Message;
}

/**
 * Derive the `render_a2ui` calls still awaiting an acknowledging tool result
 * from a persisted message history.
 *
 * A render call is pending when no `tool` message answers its id (the same
 * rule as the A2UI middleware's `findPendingToolCalls`). Because the history
 * is the source of truth, this re-derivation also restores pending calls that
 * live streaming never saw in this browser — after a page reload, or when
 * another participant's run rendered the surface — so a user action can always
 * be delivered as the acted-on call's tool result.
 */
function derivePendingRenderCalls(messages: Message[]): PendingRenderCall[] {
  const answeredIds = new Set<string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.toolCallId) answeredIds.add(msg.toolCallId);
  }
  const pending: PendingRenderCall[] = [];
  for (const msg of messages) {
    if (msg.role !== "assistant" || !msg.toolCalls) continue;
    for (const tc of msg.toolCalls) {
      if (tc.function.name !== RENDER_A2UI_TOOL_NAME || answeredIds.has(tc.id)) continue;
      const args = parseToolArgs(tc.function.arguments);
      const surfaceId = typeof args?.surfaceId === "string" ? args.surfaceId : null;
      pending.push({ toolCallId: tc.id, surfaceId });
    }
  }
  return pending;
}

/**
 * Reconstruct activity messages from the client-tool calls embedded in assistant messages.
 *
 * When resuming a session, the backend returns raw AG-UI messages. Tool calls are stored on
 * assistant messages, not as standalone activity messages. This generator re-synthesizes the
 * activity messages — A2UI surfaces (``render_a2ui``), approval controls (``render_approval``),
 * and user-added MCP tool calls (``call_mcp_tool``) — so resumed sessions display them
 * identically to live sessions. Internal A2Flow tool calls are intentionally not reproduced.
 * The synthesized message IDs mirror the ones used during live streaming so
 * ``addActivityMessage``'s upsert logic works.
 */
function* synthesizeActivityMessages(messages: Message[]): Generator<Message> {
  for (const msg of messages) {
    yield msg;
    if (msg.role !== "assistant" || !msg.toolCalls) continue;
    for (const tc of msg.toolCalls) {
      const args = parseToolArgs(tc.function.arguments);
      if (args === null) continue;
      let synthesized: Message | null = null;
      if (tc.function.name === RENDER_A2UI_TOOL_NAME) {
        synthesized = synthesizeA2UIActivityMessage(tc.id, args);
      } else if (tc.function.name === RENDER_APPROVAL_TOOL_NAME) {
        synthesized = synthesizeApprovalActivityMessage(tc.id, args);
      } else if (tc.function.name === CALL_MCP_TOOL_NAME) {
        synthesized = synthesizeMcpToolActivityMessage(tc.id, args);
      }
      if (synthesized) yield synthesized;
    }
  }
}

/** Redux state shape for the active chat session. */
interface ChatState {
  /** All messages in the current session (user, assistant, and activity). */
  messages: Message[];
  /** The active ADK session ID, or null when no session is open. */
  sessionId: string | null;
  /** True while an agent run is in progress (blocks sending new messages). */
  isRunning: boolean;
  /** True while the assistant is actively streaming text tokens. */
  isStreaming: boolean;
  /** Non-null when the last agent run produced an error. */
  error: string | null;
  /** render_a2ui calls awaiting an acknowledging tool result on the next agent run. */
  pendingRenderCalls: PendingRenderCall[];
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  isRunning: false,
  isStreaming: false,
  error: null,
  pendingRenderCalls: [],
};

const chatSlice = createSlice({
  name: "chat",
  initialState,
  reducers: {
    setSession(state, action: PayloadAction<string | null>) {
      state.sessionId = action.payload;
      state.messages = [];
      state.isRunning = false;
      state.isStreaming = false;
      state.error = null;
      state.pendingRenderCalls = [];
    },
    resumeSession(state, action: PayloadAction<{ sessionId: string; messages: Message[] }>) {
      state.sessionId = action.payload.sessionId;
      state.messages = [...synthesizeActivityMessages(action.payload.messages)];
      state.isRunning = false;
      state.isStreaming = false;
      state.error = null;
      // The persisted history is the source of truth for unacknowledged render
      // calls: re-deriving them keeps calls still pending across polls, and
      // restores calls this browser never streamed (page reload, or a surface
      // rendered by another participant's run) so a later user action can
      // still be delivered as the acted-on call's tool result.
      state.pendingRenderCalls = derivePendingRenderCalls(action.payload.messages);
    },
    addUserMessage(state, action: PayloadAction<{ id: string; content: string }>) {
      state.messages.push({
        id: action.payload.id,
        role: "user",
        content: action.payload.content,
      });
      state.isRunning = true;
      state.error = null;
    },
    startAssistantMessage(state, action: PayloadAction<string>) {
      state.messages.push({
        id: action.payload,
        role: "assistant",
        content: "",
      });
      state.isStreaming = true;
    },
    appendDelta(state, action: PayloadAction<{ messageId: string; delta: string }>) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId);
      if (msg && msg.role === "assistant") msg.content = (msg.content ?? "") + action.payload.delta;
    },
    endAssistantMessage(state) {
      state.isStreaming = false;
    },
    addActivityMessage(
      state,
      action: PayloadAction<{ id: string; activityType: string; content: Record<string, unknown> }>
    ) {
      const existing = state.messages.find((m) => m.id === action.payload.id);
      if (existing && existing.role === "activity") {
        existing.content = action.payload.content;
      } else {
        state.messages.push({
          id: action.payload.id,
          role: "activity",
          activityType: action.payload.activityType,
          content: action.payload.content,
        });
      }
    },
    startRun(state) {
      state.isRunning = true;
      state.error = null;
    },
    finishRun(state) {
      state.isRunning = false;
      state.isStreaming = false;
    },
    setError(state, action: PayloadAction<string>) {
      state.error = action.payload;
      state.isRunning = false;
      state.isStreaming = false;
    },
    clearError(state) {
      state.error = null;
    },
    addPendingRenderCall(state, action: PayloadAction<PendingRenderCall>) {
      state.pendingRenderCalls.push(action.payload);
    },
    clearPendingRenderCalls(state) {
      state.pendingRenderCalls = [];
    },
  },
});

export const {
  setSession,
  resumeSession,
  addUserMessage,
  startAssistantMessage,
  appendDelta,
  endAssistantMessage,
  addActivityMessage,
  startRun,
  finishRun,
  setError,
  clearError,
  addPendingRenderCall,
  clearPendingRenderCalls,
} = chatSlice.actions;

export default chatSlice.reducer;
