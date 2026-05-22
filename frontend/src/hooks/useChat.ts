"use client";

import { type A2UIUserAction, RENDER_A2UI_TOOL_NAME } from "@ag-ui/a2ui-middleware";
import type { AgentSubscriber } from "@ag-ui/client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";
import { useStore } from "react-redux";
import { createChatAgent, getSessionMessages } from "@/lib/api";
import { logAgUiEvent } from "@/lib/devEventLogger";
import logger from "@/lib/logger";
import type { AppDispatch, RootState } from "@/store";
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
  startRun,
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

function formatActionContent(action: A2UIUserAction): string {
  const name = action.name ?? "unknown_action";
  const surfaceId = action.surfaceId ?? "unknown_surface";
  let text = `User performed action "${name}" on surface "${surfaceId}"`;
  if (action.sourceComponentId) text += ` (component: ${action.sourceComponentId})`;
  text += `. Context: ${action.context ? JSON.stringify(action.context) : "{}"}`;
  return text;
}

export function useChat(initialSessionId: string | null) {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, sessionId, userId, isRunning, isStreaming, error } = useAppSelector(
    (s) => s.chat
  );
  const pendingRenderToolCallIds = useRef<string[]>([]);

  useEffect(() => {
    if (initialSessionId === null) {
      // /new-session route — clear any leftover state from a previous session
      // so the chat panel renders empty and sendMessage sees a null sessionId.
      dispatch(setSession(null));
      return;
    }
    // After router.replace from /new-session, the page remounts with the same id
    // already in Redux from the optimistic sendMessage path — preserve the in-flight stream.
    if (store.getState().chat.sessionId === initialSessionId) return;
    dispatch(setSession(initialSessionId));
    getSessionMessages(initialSessionId, userId)
      .then((messages) => dispatch(resumeSession({ sessionId: initialSessionId, messages })))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, initialSessionId, dispatch]);

  const switchSession = useCallback(
    (targetSessionId: string) => {
      if (isRunning) return;
      router.push(`/sessions/${targetSessionId}`);
    },
    [isRunning, router]
  );

  const newSession = useCallback(() => {
    if (isRunning) return;
    router.push("/new-session");
  }, [isRunning, router]);

  const onSessionDeleted = useCallback(
    (deletedId: string) => {
      if (deletedId === sessionId) {
        router.push("/new-session");
      }
    },
    [sessionId, router]
  );

  const sendMessage = useCallback(
    async (prompt: string) => {
      if (isRunning) return;

      let activeSessionId = sessionId;
      if (!activeSessionId) {
        activeSessionId = crypto.randomUUID();
        dispatch(setSession(activeSessionId));
        router.replace(`/sessions/${activeSessionId}`);
      }

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content: prompt }));

      const agent = createChatAgent(activeSessionId);

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
    [sessionId, userId, isRunning, dispatch, router]
  );

  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createChatAgent(sessionId);
      const content = formatActionContent(action);

      for (const tcId of pendingRenderToolCallIds.current) {
        agent.addMessage({ id: crypto.randomUUID(), role: "tool", toolCallId: tcId, content });
      }
      pendingRenderToolCallIds.current = [];

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
    [sessionId, userId, isRunning, dispatch]
  );

  return {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    sendMessage,
    sendA2uiAction,
    switchSession,
    newSession,
    onSessionDeleted,
  };
}
