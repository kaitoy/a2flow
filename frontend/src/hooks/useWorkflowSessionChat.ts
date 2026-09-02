"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "react-redux";
import {
  buildRenderAckMessages,
  buildToolCallCarrierMessage,
  type PendingRenderCall,
} from "@/lib/a2uiAction";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import {
  createDesignSessionAgent,
  createWorkflowSessionAgent,
  getDesignSessionHistory,
  getUsersByIds,
  getWorkflowSessionHistory,
  isForbiddenError,
  listWorkflowTasks,
  type SessionHistory,
  SUPPRESS_FORBIDDEN_TOAST,
  type User,
  type WorkflowTask,
} from "@/lib/api";
import {
  APPROVAL_ACTIVITY_TYPE,
  RENDER_APPROVAL_TOOL,
  RENDER_APPROVAL_TOOL_NAME,
} from "@/lib/approvalTool";
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
  syncPolledMessages,
} from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** How often (ms) to poll the shared workflow chat for new messages. */
const POLL_INTERVAL_MS = 10_000;

/**
 * A message's identifier as far as comparing two fetches of the same history
 * goes.
 *
 * `tool` messages are the exception: the backend mints them a fresh random id on
 * every fetch (they are rebuilt from their event, and only the `toolCallId` they
 * answer survives a round trip), so keying on `id` there would make an unchanged
 * history look new on every poll.
 */
function stableId(message: Message | undefined): string {
  if (!message) return "";
  return message.role === "tool" ? `tool:${message.toolCallId}` : message.id;
}

/**
 * A signature identifying a fetched history, used to skip re-applying one that
 * hasn't changed. The shared chat is append-only, so its length plus its last
 * message's {@link stableId} is enough to tell two fetches apart.
 */
function historySignature(messages: Message[]): string {
  return `${messages.length}:${stableId(messages.at(-1))}`;
}

/**
 * Build the workflow-execution AG-UI subscriber: the shared subscriber plus an
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
 * Which session-scoped chat backend the hook talks to: a workflow session (the
 * chat a workflow execution runs in, shared with its approvers) or a design
 * session (the chat that refines a workflow's task templates, shared with the
 * tenant's other developers).
 */
export type SessionChatVariant = "workflow" | "design";

/**
 * Manage the agent interaction for a workflow session or a design session.
 *
 * Neither chat has a record of its own, so both are addressed by their parent:
 * `parentId` is a WorkflowExecution id for the `"workflow"` variant and a
 * Workflow id for the `"design"` one.
 *
 * On mount, loads prior message history and — when `kickoffPrompt` is non-null
 * and the session is new — auto-sends it to start the run; design sessions
 * pass `null` because their first exchange happened in the background
 * generation run (or the user types it). Subsequent user messages and A2UI
 * user actions (e.g. a button click inside a rendered surface) are routed to
 * the session's dedicated agent endpoint, selected by `variant`. A FORBIDDEN
 * (403) failure on that initial load surfaces as the returned `forbidden`
 * flag instead of retrying or auto-sending the kickoff prompt.
 *
 * Both chats are shared, so the history is re-fetched every
 * {@link POLL_INTERVAL_MS} and messages from other participants appear without
 * a reload: a workflow session's execution initiator, its approvers, and the
 * agent all post into it; a design session's is every developer in the tenant,
 * plus the background generation run. Polling pauses while the current viewer's
 * own run is in flight and skips re-applying an unchanged history — see
 * {@link historySignature} for what counts as unchanged. The viewer's own run
 * ends with the same re-read, which reconciles the ids the live stream minted
 * with the persisted ones without disturbing a single bubble.
 *
 * Sender attribution is loaded for both variants so each message can show who
 * sent it, and it rides on the same `/messages` response as the history rather
 * than costing a request of its own. Task association is workflow-session-only —
 * a design session edits task *templates*, which the page fetches itself, rather
 * than working through the status-ful tasks a run produces.
 */
export function useWorkflowSessionChat(
  parentId: string,
  sessionId: string,
  kickoffPrompt: string | null,
  ownerUserId: string,
  variant: SessionChatVariant = "workflow"
) {
  const isDesign = variant === "design";
  const fetchHistory = isDesign ? getDesignSessionHistory : getWorkflowSessionHistory;
  const buildAgent = isDesign ? createDesignSessionAgent : createWorkflowSessionAgent;
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, isRunning, isStreaming, error, pendingRenderCalls } = useAppSelector(
    (s) => s.chat
  );
  const autoSentRef = useRef(false);
  // The session the mount effect has already initialized. React StrictMode (and
  // Fast Refresh) mount, unmount, then remount in development, re-invoking the
  // mount effect for the same session; guarding on this stops the repeat run
  // from calling setSession again — which would clear the just-auto-sent prompt
  // while autoSentRef (already set) suppressed re-sending it, so the workflow
  // prompt vanished moments after appearing (before the first poll).
  const initializedSessionRef = useRef<string | null>(null);
  // Per-message sender attribution for the shared chat: a map from message id
  // to the sender's user id, and the resolved sender User records (always
  // including the owner, for the fallback below).
  const [messageSenders, setMessageSenders] = useState<Map<string, string>>(new Map());
  const [senderUsers, setSenderUsers] = useState<Map<string, User>>(new Map());
  // Per-message task association (message id -> WorkflowTask id) and the session's
  // WorkflowTasks, used to render the task timeline and the in-chat task dividers.
  const [messageTasks, setMessageTasks] = useState<Map<string, string>>(new Map());
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  // Set when the initial history load is rejected with a FORBIDDEN (403) --
  // the caller renders AccessDeniedState instead of the chat UI.
  const [forbidden, setForbidden] = useState(false);
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
  // Raised after the viewer's own run so the next poll re-applies the history
  // even though it is unchanged — see resyncAfterRun for why that is needed.
  const reapplyAfterRunRef = useRef(false);

  /**
   * Apply the attribution a fetched history carries: the sender and task maps
   * themselves, the User records they name, and the session's WorkflowTasks.
   *
   * The two maps come back on the history's own records, so they cost no extra
   * request; only the User records and the task list are fetched separately.
   */
  const applyAttribution = useCallback(
    async (history: SessionHistory) => {
      setMessageSenders(history.senders);
      setMessageTasks(history.tasks);
      const [users, taskList] = await Promise.all([
        // The owner is resolved too, even when they sent nothing: unattributed
        // messages fall back to them.
        getUsersByIds([ownerUserId, ...history.senders.values()]),
        // Design sessions edit the workflow's task templates, which the page
        // fetches itself; there are no status-ful session tasks to track here.
        isDesign ? Promise.resolve<WorkflowTask[]>([]) : listWorkflowTasks(parentId),
      ]);
      setSenderUsers(users);
      if (!isDesign) setTasks(taskList);
    },
    [parentId, ownerUserId, isDesign]
  );

  /**
   * Re-read the shared history and reconcile it with what is on screen.
   *
   * One `/messages` request serves the transcript, the sender attribution and
   * the task association alike, since the backend folds all three into the same
   * records.
   */
  const refreshHistory = useCallback(async () => {
    // Never merge mid-run: syncPolledMessages rebuilds the message array from the
    // fetched history and resets the streaming flags, which would clobber a live
    // stream, so polling is only safe between runs.
    if (isRunningRef.current || isStreamingRef.current) return;
    try {
      const history = await fetchHistory(parentId);
      // A run may have started while the fetch was in flight; re-check the guard.
      if (isRunningRef.current || isStreamingRef.current) return;
      // Skip re-applying an unchanged fetch — it costs two more requests and a
      // re-render for nothing. The run-follow-up below is the one exception.
      const signature = historySignature(history.messages);
      if (signature === appliedSignatureRef.current && !reapplyAfterRunRef.current) return;
      reapplyAfterRunRef.current = false;
      appliedSignatureRef.current = signature;
      // Merge (don't replace): every bubble already on screen keeps the React key
      // it was drawn under, so reconciling the live stream's ids with the
      // persisted ones costs no remount — see syncPolledMessages.
      dispatch(syncPolledMessages({ sessionId, messages: history.messages }));
      await applyAttribution(history);
    } catch (err) {
      logger.error(err, "failed to refresh session history");
    }
  }, [parentId, sessionId, dispatch, applyAttribution, fetchHistory]);

  /**
   * Re-read the history the moment the viewer's own run ends, and ask the next
   * poll to read it once more.
   *
   * The backend records sender attribution and task association *after* the last
   * event of the stream, so this read — which fires as soon as `runAgent`
   * resolves — can land a beat too early and see the run's messages with neither.
   * Nothing about the messages changes afterwards, so without the follow-up the
   * signature guard would skip every later poll and freeze that miss until a
   * reload: the chat would keep showing the run's messages under the previous
   * task's heading. The flag is raised only once this read has settled, so the
   * read itself can't consume it, and re-applying costs nothing visible now that
   * a poll leaves every bubble in place.
   */
  const resyncAfterRun = useCallback(() => {
    // refreshHistory guards on isRunningRef/isStreamingRef, which only sync to
    // Redux on the next render; set them directly so the resync doesn't bail out
    // on the stale pre-finishRun value.
    isRunningRef.current = false;
    isStreamingRef.current = false;
    void refreshHistory().then(() => {
      reapplyAfterRunRef.current = true;
    });
  }, [refreshHistory]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendMessage = useCallback(
    async (prompt: string) => {
      if (!sessionId || isRunning) return;

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content: prompt }));
      locallySentIds.current.add(msgId);

      const agent = buildAgent(parentId, sessionId);

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
      // Everything the run produced is now persisted with its sender and its
      // task association; re-read it all in one pass. The rendered bubbles keep
      // their keys, so reconciling their ids with the persisted ones is invisible.
      resyncAfterRun();
    },
    [parentId, sessionId, isRunning, dispatch, resyncAfterRun, buildAgent]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction, values: Record<string, unknown>) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = buildAgent(parentId, sessionId);

      // The action rides as the tool result of the render call that produced
      // the acted-on surface, carrying `values` (the surface's data model) so
      // the agent sees what the user entered; other pending calls get the no-op
      // ack, so the backend attributes only the acted-on call to this user.
      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending, action, values)) {
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
      // Resync the full history (not just the sender map): the just-resolved
      // A2UI card's live-stamped sourceToolCallId can differ from the id the
      // backend persisted (ADK remaps long-running client-tool ids between the
      // streamed and persisted events), so re-deriving it from /messages via
      // the same resumed-history path keeps it consistent with the sender map.
      resyncAfterRun();
    },
    [parentId, sessionId, isRunning, dispatch, refreshHistory, buildAgent]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendApprovalResult = useCallback(
    async (toolCallId: string, decision: "approved" | "rejected" | "returned") => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createWorkflowSessionAgent(parentId, sessionId);

      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending)) {
        agent.addMessage(ack);
      }
      if (pending.length > 0) dispatch(clearPendingRenderCalls());

      // The approval tool's result resumes the agent run with the decision. It
      // needs its own carrier for the same reason the A2UI acks do: without the
      // issuing tool call in `messages`, ag-ui-adk names the FunctionResponse
      // "unknown" and the provider rejects the run.
      agent.addMessage(
        buildToolCallCarrierMessage([{ toolCallId, name: RENDER_APPROVAL_TOOL_NAME }])
      );
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
      // The decision's tool result is now persisted with its sender, and the
      // agent may have advanced tasks while resuming after it; one resync shows
      // the decider's avatar and the new task state without waiting for a poll.
      resyncAfterRun();
    },
    [parentId, sessionId, isRunning, dispatch, resyncAfterRun]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: sendMessage intentionally omitted — it changes on every isRunning flip and the init guard below prevents double-sends
  useEffect(() => {
    // Initialize each session exactly once. A repeat run for the same session
    // (StrictMode/Fast Refresh remount) is a no-op, so it can't clear the
    // optimistically-rendered prompt; a genuine session change re-initializes.
    if (initializedSessionRef.current === sessionId) return;
    initializedSessionRef.current = sessionId;
    autoSentRef.current = false;
    appliedSignatureRef.current = null;
    reapplyAfterRunRef.current = false;
    setForbidden(false);
    dispatch(setSession(sessionId));
    fetchHistory(parentId, SUPPRESS_FORBIDDEN_TOAST)
      .then((history) => {
        const loadedMessages = history.messages;
        dispatch(resumeSession({ sessionId, messages: loadedMessages }));
        // Record the loaded history so the first poll doesn't re-apply it.
        appliedSignatureRef.current = historySignature(loadedMessages);
        // Catches its own failure: a rejection here must not reach the catch
        // below, which would read it as a missing session and auto-send.
        void applyAttribution(history).catch((err: unknown) => {
          logger.error(err, "failed to load session attribution");
        });
        if (kickoffPrompt !== null && loadedMessages.length === 0 && !autoSentRef.current) {
          autoSentRef.current = true;
          sendMessage(kickoffPrompt);
        }
      })
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        // ADK session not yet created (first run) — auto-send to kick off the workflow
        if (kickoffPrompt !== null && !autoSentRef.current) {
          autoSentRef.current = true;
          sendMessage(kickoffPrompt);
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
      if (active) void refreshHistory();
    }, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sessionId, refreshHistory]);

  return {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    pendingRenderCalls,
    sendMessage,
    sendA2uiAction,
    sendApprovalResult,
    messageSenders,
    senderUsers,
    locallySentMessageIds: locallySentIds.current,
    messageTasks,
    tasks,
    forbidden,
  };
}
