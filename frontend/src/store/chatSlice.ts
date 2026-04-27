import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming: boolean;
  a2uiPayload?: string;
}

interface ChatState {
  messages: Message[];
  sessionId: string | null;
  userId: string;
  isRunning: boolean;
  error: string | null;
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  userId: 'user',
  isRunning: false,
  error: null,
};

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setSession(state, action: PayloadAction<string>) {
      state.sessionId = action.payload;
    },
    addUserMessage(state, action: PayloadAction<{ id: string; content: string }>) {
      state.messages.push({
        id: action.payload.id,
        role: 'user',
        content: action.payload.content,
        isStreaming: false,
      });
      state.isRunning = true;
      state.error = null;
    },
    startAssistantMessage(state, action: PayloadAction<string>) {
      state.messages.push({
        id: action.payload,
        role: 'assistant',
        content: '',
        isStreaming: true,
      });
    },
    appendDelta(state, action: PayloadAction<{ messageId: string; delta: string }>) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId);
      if (msg) msg.content += action.payload.delta;
    },
    endAssistantMessage(state, action: PayloadAction<string>) {
      const msg = state.messages.find((m) => m.id === action.payload);
      if (msg) msg.isStreaming = false;
    },
    addA2uiMessage(state, action: PayloadAction<{ id: string; payload: unknown }>) {
      const existing = state.messages.find((m) => m.id === action.payload.id);
      if (existing) {
        existing.a2uiPayload = JSON.stringify(action.payload.payload);
      } else {
        state.messages.push({
          id: action.payload.id,
          role: 'assistant',
          content: '',
          isStreaming: false,
          a2uiPayload: JSON.stringify(action.payload.payload),
        });
      }
    },
    startRun(state) {
      state.isRunning = true;
      state.error = null;
    },
    finishRun(state) {
      state.isRunning = false;
      // safety: clear any lingering isStreaming flags
      state.messages.forEach((m) => {
        m.isStreaming = false;
      });
    },
    setError(state, action: PayloadAction<string>) {
      state.error = action.payload;
      state.isRunning = false;
      state.messages.forEach((m) => {
        m.isStreaming = false;
      });
    },
    clearError(state) {
      state.error = null;
    },
  },
});

export const {
  setSession,
  addUserMessage,
  startAssistantMessage,
  appendDelta,
  endAssistantMessage,
  addA2uiMessage,
  startRun,
  finishRun,
  setError,
  clearError,
} = chatSlice.actions;

export default chatSlice.reducer;
