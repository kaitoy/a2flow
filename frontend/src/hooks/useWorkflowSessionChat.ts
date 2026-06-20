"use client";

import { useCallback, useEffect, useRef } from "react";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import { createWorkflowSessionAgent, getSessionMessages } from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE, RENDER_APPROVAL_TOOL } from "@/lib/approvalTool";
import logger from "@/lib/logger";
import type { AppDispatch } from "@/store";
import {
  addActivityMessage,
  addUserMessage,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startRun,
} from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/**
 * Build the workflow-session AG-UI subscriber: the shared subscriber plus an
 * approval-rendering handler that turns `render_approval` tool calls into
 * approval-control activity messages.
 *
 * @param dispatch - The Redux dispatch used to apply the mapped actions.
 * @param onRenderA2uiEnd - Called with the tool call ID whenever a RENDER_A2UI
 *   tool call ends, so the next agent run can acknowledge the render.
 */
function makeEventHandlers(dispatch: AppDispatch, onRenderA2uiEnd: (toolCallId: string) => void) {
  return createAgentSubscriber(dispatch, {
    onRenderA2uiEnd,
    onRenderApprovalEnd: (toolCallId, args) => {
      // Render approve/reject controls; the decision is sent back as this
      // tool's result by sendApprovalResult, so it is not auto-acknowledged.
      const { approvalId, title, description } = args as {
        approvalId?: string;
        title?: string;
        description?: string;
      };
      if (approvalId) {
        dispatch(
          addActivityMessage({
            id: toolCallId,
            activityType: APPROVAL_ACTIVITY_TYPE,
            content: { approvalId, title, description },
          })
        );
      }
    },
  });
}

/**
 * Manage the agent interaction for a workflow session.
 *
 * On mount, loads prior message history and auto-sends the workflow prompt if the session is new.
 * Subsequent user messages are routed to the workflow session's dedicated agent endpoint.
 */
export function useWorkflowSessionChat(
  workflowSessionId: string,
  sessionId: string,
  workflowPrompt: string
) {
  const dispatch = useAppDispatch();
  const { messages, isRunning, isStreaming, error } = useAppSelector((s) => s.chat);
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
          { tools: [RENDER_APPROVAL_TOOL] },
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
    [workflowSessionId, sessionId, isRunning, dispatch]
  );

  const sendApprovalResult = useCallback(
    async (toolCallId: string, decision: "approved" | "rejected") => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

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

      // The approval tool's result resumes the agent run with the decision.
      agent.addMessage({
        id: crypto.randomUUID(),
        role: "tool",
        toolCallId,
        content: decision,
      });

      try {
        await agent.runAgent(
          { tools: [RENDER_APPROVAL_TOOL] },
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
    [workflowSessionId, sessionId, isRunning, dispatch]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: sendMessage intentionally omitted — it changes on every isRunning flip and autoSentRef guards against double-sends
  useEffect(() => {
    dispatch(setSession(sessionId));
    getSessionMessages(sessionId)
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
  }, [sessionId, dispatch]);

  return {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    sendMessage,
    sendApprovalResult,
  };
}
