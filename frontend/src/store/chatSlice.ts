import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type { Message };

/**
 * Reconstruct A2UI activity messages from RENDER_A2UI tool calls embedded in assistant messages.
 *
 * When resuming a session, the backend returns raw AG-UI messages. Tool calls are stored on
 * assistant messages, not as standalone activity messages. This generator re-synthesizes the
 * activity messages so resumed sessions display A2UI surfaces identically to live sessions.
 * The synthesized message IDs mirror the format used by A2UIMiddleware during live streaming
 * so the upsert logic in ``addActivityMessage`` works correctly if a surface is later updated.
 */
function* synthesizeA2UIActivityMessages(messages: Message[]): Generator<Message> {
  for (const msg of messages) {
    yield msg;
    if (msg.role !== "assistant" || !msg.toolCalls) continue;
    for (const tc of msg.toolCalls) {
      if (tc.function.name !== RENDER_A2UI_TOOL_NAME) continue;
      let args: Record<string, unknown>;
      try {
        args = JSON.parse(
          typeof tc.function.arguments === "string"
            ? tc.function.arguments
            : JSON.stringify(tc.function.arguments)
        );
      } catch {
        continue;
      }
      const { surfaceId, catalogId, components, data } = args as {
        surfaceId?: string;
        catalogId?: string;
        components?: unknown[];
        data?: unknown;
      };
      if (!surfaceId) continue;
      const ops: Record<string, unknown>[] = [
        { version: "v0.9", createSurface: { surfaceId, catalogId } },
        { version: "v0.9", updateComponents: { surfaceId, components: components ?? [] } },
      ];
      if (data != null) ops.push({ version: "v0.9", updateDataModel: { surfaceId, value: data } });
      yield {
        // ID format mirrors A2UIMiddleware's live-streaming synthesis:
        //   messageId = `a2ui-surface-${surfaceId}-${toolCallId}`
        // Keeping the same format ensures addActivityMessage's upsert logic
        // (which matches by id) works correctly if a surface is later updated.
        id: `a2ui-surface-${surfaceId}-${tc.id}`,
        role: "activity",
        activityType: A2UIActivityType,
        content: { [A2UI_OPERATIONS_KEY]: ops },
      } as Message;
    }
  }
}

/** Redux state shape for the active chat session. */
interface ChatState {
  /** All messages in the current session (user, assistant, and activity). */
  messages: Message[];
  /** The active ADK session ID, or null when no session is open. */
  sessionId: string | null;
  /** The current user's identifier, sent as forwarded props to the agent. */
  userId: string;
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
  userId: "user",
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
      state.messages = [...synthesizeA2UIActivityMessages(action.payload.messages)];
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
