'use client';

import { useCallback, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  setSession,
  addUserMessage,
  startAssistantMessage,
  appendDelta,
  endAssistantMessage,
  addA2uiMessage,
  finishRun,
  setError,
} from '@/store/chatSlice';
import { createSession, createChatAgent } from '@/lib/api';
import logger from '@/lib/logger';
import { logAgUiEvent } from '@/lib/devEventLogger';

export function useChat() {
  const dispatch = useAppDispatch();
  const { messages, sessionId, userId, isRunning, error } = useAppSelector(
    (s) => s.chat,
  );

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
      agent.addMessage({ id: msgId, role: 'user', content: prompt });

      const a2uiToolCallIds = new Set<string>();

      try {
        await agent.runAgent(
          { forwardedProps: { userId } },
          {
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
            onToolCallStartEvent: async ({ event }) => {
              if (event.toolCallName === 'send_a2ui_json_to_client') {
                a2uiToolCallIds.add(event.toolCallId);
              }
            },
            onToolCallResultEvent: async ({ event }) => {
              if (!a2uiToolCallIds.has(event.toolCallId)) return;
              a2uiToolCallIds.delete(event.toolCallId);
              try {
                const result = JSON.parse(event.content) as Record<string, unknown>;
                const payload = result['validated_a2ui_json'];
                if (payload != null) {
                  dispatch(addA2uiMessage({ id: event.messageId, payload }));
                }
              } catch (e) {
                logger.error(e, 'failed to parse A2UI payload');
              }
            },
            onRunErrorEvent: async ({ event }) => {
              dispatch(setError(event.message));
            },
          },
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

  return { messages, isRunning, error, sendMessage };
}
