"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "react-redux";
import { buildRenderAckMessages, type PendingRenderCall } from "@/lib/a2uiAction";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import {
  createWorkflowSessionAgent,
  getUsersByIds,
  getWorkflowSessionMessageSenders,
  getWorkflowSessionMessages,
  getWorkflowSessionMessageTasks,
  listWorkflowTasks,
  type User,
  type WorkflowTask,
} from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE, RENDER_APPROVAL_TOOL } from "@/lib/approvalTool";
import logger from "@/lib/logger";
import type { AppDispatch, RootState } from "@/store";
import {
  addActivityMessage,
  addPendingRenderCall,
  addUserMessage,
  clearPendingRenderCalls,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startRun,
} from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** How often (ms) to poll the shared workflow chat for new messages. */
const POLL_INTERVAL_MS = 10_000;

/**
 * Build the workflow-session AG-UI subscriber: the shared subscriber plus an
 * approval-rendering handler that turns `render_approval` tool calls into
 * approval-control activity messages.
 *
 * @param dispatch - The Redux dispatch used to apply the mapped actions.
 * @param onRenderA2uiEnd - Called with the pending render call (tool call ID
 *   plus rendered surfaceId) whenever a RENDER_A2UI tool call ends, so the next
 *   agent run can acknowledge the render.
 */
function makeEventHandlers(
  dispatch: AppDispatch,
  onRenderA2uiEnd: (call: PendingRenderCall) => void
) {
  return createAgentSubscriber(dispatch, {
    onRenderA2uiEnd: (toolCallId, args) => {
      const surfaceId = typeof args.surfaceId === "string" ? args.surfaceId : null;
      onRenderA2uiEnd({ toolCallId, surfaceId });
    },
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
 * Subsequent user messages and A2UI user actions (e.g. a button click inside a
 * rendered surface) are routed to the workflow session's dedicated agent endpoint.
 *
 * Because the chat is shared (owner, approvers, and the agent all post into it),
 * the history is also re-fetched every {@link POLL_INTERVAL_MS} so messages from
 * other participants appear without a reload. Polling pauses while the current
 * viewer's own run is in flight and skips re-applying an unchanged history.
 */
export function useWorkflowSessionChat(
  workflowSessionId: string,
  sessionId: string,
  workflowPrompt: string,
  ownerUserId: string
) {
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, isRunning, isStreaming, error } = useAppSelector((s) => s.chat);
  const autoSentRef = useRef(false);
  // Per-message sender attribution for the shared workflow chat: a map from
  // message id to the sender's user id, and the resolved sender User records
  // (always including the owner, for the fallback below).
  const [messageSenders, setMessageSenders] = useState<Map<string, string>>(new Map());
  const [senderUsers, setSenderUsers] = useState<Map<string, User>>(new Map());
  // Per-message task association (message id -> WorkflowTask id) and the session's
  // WorkflowTasks, used to render the task timeline and the in-chat task dividers.
  const [messageTasks, setMessageTasks] = useState<Map<string, string>>(new Map());
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  // Ids of user messages the current viewer sent this session. Their optimistic
  // client ids differ from the persisted ADK event ids, so they are absent from
  // `messageSenders`; the UI attributes them to the current user until a reload
  // replaces them with the persisted, attributed history.
  const locallySentIds = useRef<Set<string>>(new Set());
  // Live run state mirrored into refs so the polling interval reads the latest
  // value without being torn down and recreated on every render.
  const isRunningRef = useRef(isRunning);
  isRunningRef.current = isRunning;
  const isStreamingRef = useRef(isStreaming);
  isStreamingRef.current = isStreaming;
  // Signature of the message history last applied to the store, so an idle poll
  // (no new messages) skips the redundant resumeSession dispatch and re-render.
  const appliedSignatureRef = useRef<string | null>(null);

  const refreshSenders = useCallback(async () => {
    try {
      const senders = await getWorkflowSessionMessageSenders(workflowSessionId);
      const users = await getUsersByIds([ownerUserId, ...senders.values()]);
      setMessageSenders(senders);
      setSenderUsers(users);
    } catch (err) {
      logger.error(err, "failed to load message senders");
    }
  }, [workflowSessionId, ownerUserId]);

  const refreshTasks = useCallback(async () => {
    try {
      const [taskList, taskMap] = await Promise.all([
        listWorkflowTasks(workflowSessionId),
        getWorkflowSessionMessageTasks(workflowSessionId),
      ]);
      setTasks(taskList);
      setMessageTasks(taskMap);
    } catch (err) {
      logger.error(err, "failed to load workflow tasks");
    }
  }, [workflowSessionId]);

  const refreshMessages = useCallback(async () => {
    // Never clobber an in-flight run: resumeSession replaces the whole message
    // array and resets the streaming flags, so polling is only safe between runs.
    if (isRunningRef.current || isStreamingRef.current) return;
    try {
      const loaded = await getWorkflowSessionMessages(workflowSessionId);
      // A run may have started while the fetch was in flight; re-check the guard.
      if (isRunningRef.current || isStreamingRef.current) return;
      // The shared chat is append-only, so length + last id uniquely identify the
      // history; skip re-applying an unchanged fetch to avoid a needless scroll.
      const signature = `${loaded.length}:${loaded.at(-1)?.id ?? ""}`;
      if (signature === appliedSignatureRef.current) return;
      appliedSignatureRef.current = signature;
      dispatch(resumeSession({ sessionId, messages: loaded }));
      // Keep sender avatars and the task timeline/groups in sync with the newly
      // visible messages.
      await Promise.all([refreshSenders(), refreshTasks()]);
    } catch (err) {
      logger.error(err, "failed to poll workflow session messages");
    }
  }, [workflowSessionId, sessionId, dispatch, refreshSenders, refreshTasks]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!sessionId || isRunning) return;

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content: prompt }));
      locallySentIds.current.add(msgId);

      const agent = createWorkflowSessionAgent(workflowSessionId, sessionId);

      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending)) {
        agent.addMessage(ack);
      }
      if (pending.length > 0) dispatch(clearPendingRenderCalls());

      agent.addMessage({ id: msgId, role: "user", content: prompt });

      try {
        await agent.runAgent(
          { tools: [RENDER_APPROVAL_TOOL] },
          makeEventHandlers(dispatch, (call) => {
            dispatch(addPendingRenderCall(call));
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
      // The message this run sent is now persisted with its sender; refresh the
      // attribution map so reloaded history shows the correct avatar.
      void refreshSenders();
      // Refresh task state and the per-message task association the run produced.
      void refreshTasks();
    },
    [workflowSessionId, sessionId, isRunning, dispatch, refreshSenders, refreshTasks]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createWorkflowSessionAgent(workflowSessionId, sessionId);

      // The action rides as the tool result of the render call that produced
      // the acted-on surface; other pending calls get the no-op ack, so the
      // backend attributes only the acted-on call to this user.
      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending, action)) {
        agent.addMessage(ack);
      }
      if (pending.length > 0) dispatch(clearPendingRenderCalls());

      try {
        await agent.runAgent(
          { tools: [RENDER_APPROVAL_TOOL] },
          makeEventHandlers(dispatch, (call) => {
            dispatch(addPendingRenderCall(call));
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
      // refreshMessages guards on isRunningRef/isStreamingRef, which only sync
      // to Redux on the next render; set them directly so the resync below
      // doesn't bail out on the stale pre-finishRun value.
      isRunningRef.current = false;
      isStreamingRef.current = false;
      // Resync the full history (not just the sender map): the just-resolved
      // A2UI card's live-stamped sourceToolCallId can differ from the id the
      // backend persisted (ADK remaps long-running client-tool ids between the
      // streamed and persisted events), so re-deriving it from /messages via
      // the same resumed-history path keeps it consistent with the sender map.
      void refreshMessages();
    },
    [workflowSessionId, sessionId, isRunning, dispatch, refreshMessages]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendApprovalResult = useCallback(
    async (toolCallId: string, decision: "approved" | "rejected") => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createWorkflowSessionAgent(workflowSessionId, sessionId);

      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending)) {
        agent.addMessage(ack);
      }
      if (pending.length > 0) dispatch(clearPendingRenderCalls());

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
          makeEventHandlers(dispatch, (call) => {
            dispatch(addPendingRenderCall(call));
          })
        );
      } catch (err) {
        logger.error(err, "stream error");
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
      // The decision's tool result is now persisted with its sender; refresh
      // the attribution map so the approval bubble shows the decider's avatar
      // right away instead of waiting for the next poll.
      void refreshSenders();
      // The agent may have advanced tasks while resuming after the decision;
      // refresh task state and the per-message task association.
      void refreshTasks();
    },
    [workflowSessionId, sessionId, isRunning, dispatch, refreshSenders, refreshTasks]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: sendMessage intentionally omitted — it changes on every isRunning flip and autoSentRef guards against double-sends
  useEffect(() => {
    dispatch(setSession(sessionId));
    void refreshSenders();
    void refreshTasks();
    getWorkflowSessionMessages(workflowSessionId)
      .then((loadedMessages) => {
        dispatch(resumeSession({ sessionId, messages: loadedMessages }));
        // Record the loaded history so the first poll doesn't re-apply it.
        appliedSignatureRef.current = `${loadedMessages.length}:${loadedMessages.at(-1)?.id ?? ""}`;
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

  // Poll the shared chat so messages posted by other participants (and agent
  // progress made while a different person is viewing) appear without a reload.
  // The mount effect handles the first load, so the interval only covers updates.
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const id = setInterval(() => {
      if (active) void refreshMessages();
    }, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sessionId, refreshMessages]);

  return {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    sendMessage,
    sendA2uiAction,
    sendApprovalResult,
    messageSenders,
    senderUsers,
    locallySentMessageIds: locallySentIds.current,
    messageTasks,
    tasks,
  };
}
