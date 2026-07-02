"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import { useStore } from "react-redux";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import { createChatAgent, getSessionMessages } from "@/lib/api";
import logger from "@/lib/logger";
import type { RootState } from "@/store";
import {
  addPendingRenderToolCallId,
  addUserMessage,
  clearPendingRenderToolCallIds,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startRun,
} from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** Serialize an A2UIUserAction into a human-readable string sent as a user message to the agent. */
function formatActionContent(action: A2UIUserAction): string {
  const name = action.name ?? "unknown_action";
  const surfaceId = action.surfaceId ?? "unknown_surface";
  let text = `User performed action "${name}" on surface "${surfaceId}"`;
  if (action.sourceComponentId) text += ` (component: ${action.sourceComponentId})`;
  text += `. Context: ${action.context ? JSON.stringify(action.context) : "{}"}`;
  return text;
}

/**
 * Manage the active chat session and agent invocation for the general chat UI.
 *
 * Handles session initialization, message history loading on resume, sending user
 * messages, forwarding A2UI user actions, and session navigation.
 */
export function useChat(initialSessionId: string | null) {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, sessionId, isRunning, isStreaming, error } = useAppSelector((s) => s.chat);

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
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
    getSessionMessages(initialSessionId)
      .then((messages) => dispatch(resumeSession({ sessionId: initialSessionId, messages })))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSessionId, dispatch]);

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

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
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

      const pendingIds = store.getState().chat.pendingRenderToolCallIds;
      for (const tcId of pendingIds) {
        agent.addMessage({
          id: crypto.randomUUID(),
          role: "tool",
          toolCallId: tcId,
          content: "rendered",
        });
      }
      if (pendingIds.length > 0) dispatch(clearPendingRenderToolCallIds());

      agent.addMessage({ id: msgId, role: "user", content: prompt });

      try {
        await agent.runAgent(
          undefined,
          createAgentSubscriber(dispatch, {
            onRenderA2uiEnd: (tcId) => {
              dispatch(addPendingRenderToolCallId(tcId));
            },
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
    },
    [sessionId, isRunning, dispatch, router]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createChatAgent(sessionId);
      const content = formatActionContent(action);

      const pendingIds = store.getState().chat.pendingRenderToolCallIds;
      for (const tcId of pendingIds) {
        agent.addMessage({ id: crypto.randomUUID(), role: "tool", toolCallId: tcId, content });
      }
      if (pendingIds.length > 0) dispatch(clearPendingRenderToolCallIds());

      try {
        await agent.runAgent(
          undefined,
          createAgentSubscriber(dispatch, {
            onRenderA2uiEnd: (tcId) => {
              dispatch(addPendingRenderToolCallId(tcId));
            },
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
    },
    [sessionId, isRunning, dispatch]
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
