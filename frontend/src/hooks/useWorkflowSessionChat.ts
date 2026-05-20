"use client";

import { RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import type { AgentSubscriber } from "@ag-ui/client";
import { useCallback, useEffect, useRef } from "react";
import { createWorkflowSessionAgent, getSessionMessages } from "@/lib/api";
import { logAgUiEvent } from "@/lib/devEventLogger";
import logger from "@/lib/logger";
import type { AppDispatch } from "@/store";
import {
  addActivityMessage,
  addUserMessage,
  appendDelta,
  endAssistantMessage,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startAssistantMessage,
} from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function makeEventHandlers(
  dispatch: AppDispatch,
  onRenderA2uiEnd: (toolCallId: string) => void
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
      dispatch(
        addActivityMessage({
          id: event.messageId,
          activityType: event.activityType,
          content: event.content as Record<string, unknown>,
        })
      );
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

export function useWorkflowSessionChat(
  workflowSessionId: string,
  sessionId: string,
  workflowPrompt: string
) {
  const dispatch = useAppDispatch();
  const { messages, userId, isRunning, isStreaming, error } = useAppSelector((s) => s.chat);
  const pendingRenderToolCallIds = useRef<string[]>([]);
  const autoSentRef = useRef(false);

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!sessionId || isRunning) return;

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content: prompt }));

      const agent = createWorkflowSessionAgent(workflowSessionId, sessionId);

      for (const tcId of pendingRenderToolCallIds.current) {
        agent.addMessage({
          id: crypto.randomUUID(),
          role: "tool",
          toolCallId: tcId,
          content: "rendered",
        });
      }
      pendingRenderToolCallIds.current = [];

      agent.addMessage({ id: msgId, role: "user", content: prompt });

      try {
        await agent.runAgent(
          { forwardedProps: { userId } },
          makeEventHandlers(dispatch, (tcId) => {
            pendingRenderToolCallIds.current.push(tcId);
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
    },
    [workflowSessionId, sessionId, userId, isRunning, dispatch]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: sendMessage intentionally omitted — it changes on every isRunning flip and autoSentRef guards against double-sends
  useEffect(() => {
    dispatch(setSession(sessionId));
    getSessionMessages(sessionId, userId)
      .then((loadedMessages) => {
        dispatch(resumeSession({ sessionId, messages: loadedMessages }));
        if (loadedMessages.length === 0 && !autoSentRef.current) {
          autoSentRef.current = true;
          sendMessage(workflowPrompt);
        }
      })
      .catch(() => {
        // ADK session not yet created (first run) — auto-send to kick off the workflow
        if (!autoSentRef.current) {
          autoSentRef.current = true;
          sendMessage(workflowPrompt);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, userId, dispatch]);

  return {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    sendMessage,
  };
}
