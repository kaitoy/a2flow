'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  setSession,
  addUserMessage,
  startAssistantMessage,
  appendDelta,
  endAssistantMessage,
  addA2uiMessage,
  startRun,
  finishRun,
  setError,
} from '@/store/chatSlice';
import { A2UIActivityType, A2UI_OPERATIONS_KEY, RENDER_A2UI_TOOL_NAME, type A2UIUserAction } from '@ag-ui/a2ui-middleware';
import { createSession, createChatAgent } from '@/lib/api';
import logger from '@/lib/logger';
import { logAgUiEvent } from '@/lib/devEventLogger';
import type { AppDispatch } from '@/store';
import type { AgentSubscriber } from '@ag-ui/client';

function makeEventHandlers(
  dispatch: AppDispatch,
  onRenderA2uiEnd: (toolCallId: string) => void,
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
    onTextMessageEndEvent: async ({ event }) => {
      dispatch(endAssistantMessage(event.messageId));
    },
    onActivitySnapshotEvent: async ({ event }) => {
      if (event.activityType === A2UIActivityType) {
        const operations = event.content[A2UI_OPERATIONS_KEY];
        if (operations != null) {
          dispatch(addA2uiMessage({ id: event.messageId, payload: operations }));
        }
      }
    },
    onToolCallEndEvent: async ({ event, toolCallName }) => {
      if (toolCallName === RENDER_A2UI_TOOL_NAME) {
        onRenderA2uiEnd(event.toolCallId);
      }
    },
    onRunErrorEvent: async ({ event }) => {
      dispatch(setError(event.message));
    },
  };
}

function formatActionContent(action: A2UIUserAction): string {
  const name = action.name ?? 'unknown_action';
  const surfaceId = action.surfaceId ?? 'unknown_surface';
  let text = `User performed action "${name}" on surface "${surfaceId}"`;
  if (action.sourceComponentId) text += ` (component: ${action.sourceComponentId})`;
  text += `. Context: ${action.context ? JSON.stringify(action.context) : '{}'}`;
  return text;
}

export function useChat() {
  const dispatch = useAppDispatch();
  const { messages, sessionId, userId, isRunning, error } = useAppSelector(
    (s) => s.chat,
  );
  const pendingRenderToolCallIds = useRef<string[]>([]);

  useEffect(() => {
    if (sessionId) return;
    createSession(userId)
      .then((id) => dispatch(setSession(id)))
      .catch((err) => {
        logger.error(err, 'failed to create session');
        dispatch(setError('Failed to connect to the server.'));
      });
  }, [sessionId, userId, dispatch]);

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!sessionId || isRunning) return;

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content: prompt }));

      const agent = createChatAgent(sessionId);

      for (const tcId of pendingRenderToolCallIds.current) {
        agent.addMessage({ id: crypto.randomUUID(), role: 'tool', toolCallId: tcId, content: 'rendered' });
      }
      pendingRenderToolCallIds.current = [];

      agent.addMessage({ id: msgId, role: 'user', content: prompt });

      try {
        await agent.runAgent(
          { forwardedProps: { userId } },
          makeEventHandlers(dispatch, (tcId) => { pendingRenderToolCallIds.current.push(tcId); }),
        );
      } catch (err) {
        logger.error(err, 'stream error');
        dispatch(setError('An error occurred while communicating with the agent.'));
        return;
      }

      dispatch(finishRun());
    },
    [sessionId, userId, isRunning, dispatch],
  );

  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createChatAgent(sessionId);
      const content = formatActionContent(action);

      for (const tcId of pendingRenderToolCallIds.current) {
        agent.addMessage({ id: crypto.randomUUID(), role: 'tool', toolCallId: tcId, content });
      }
      pendingRenderToolCallIds.current = [];

      try {
        await agent.runAgent(
          { forwardedProps: { userId } },
          makeEventHandlers(dispatch, (tcId) => { pendingRenderToolCallIds.current.push(tcId); }),
        );
      } catch (err) {
        logger.error(err, 'stream error');
        dispatch(setError('An error occurred while communicating with the agent.'));
        return;
      }

      dispatch(finishRun());
    },
    [sessionId, userId, isRunning, dispatch],
  );

  return { messages, isRunning, error, sendMessage, sendA2uiAction };
}
