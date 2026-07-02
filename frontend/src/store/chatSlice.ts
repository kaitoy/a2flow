import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import {
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
    content: { [A2UI_OPERATIONS_KEY]: ops },
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
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  isRunning: false,
  isStreaming: false,
  error: null,
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
    },
    resumeSession(state, action: PayloadAction<{ sessionId: string; messages: Message[] }>) {
      state.sessionId = action.payload.sessionId;
      state.messages = [...synthesizeActivityMessages(action.payload.messages)];
      state.isRunning = false;
      state.isStreaming = false;
      state.error = null;
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
} = chatSlice.actions;

export default chatSlice.reducer;
