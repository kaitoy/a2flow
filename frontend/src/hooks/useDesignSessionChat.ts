"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "react-redux";
import { buildRenderAckMessages, type PendingRenderCall } from "@/lib/a2uiAction";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import {
  createDesignSessionAgent,
  getDesignSessionHistory,
  getUsersByIds,
  isForbiddenError,
  type SessionHistory,
  SUPPRESS_FORBIDDEN_TOAST,
  type User,
} from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE, RENDER_APPROVAL_TOOL } from "@/lib/approvalTool";
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

/** How often (ms) to poll the shared design chat for new messages. */
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
 * Build the design session's AG-UI subscriber: the shared subscriber plus an
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
      // Render approve/reject controls. A design agent has no approval tool of
      // its own, so this only keeps a stray call visible; it is not
      // auto-acknowledged.
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
 * Manage the agent interaction for a workflow's design session.
 *
 * A design session has no record of its own, so it is addressed by its
 * workflow. On mount, loads prior message history; subsequent user messages and
 * A2UI user actions (e.g. a button click inside a rendered surface) are sent to
 * the design session's agent endpoint, and the browser drives the run. (A
 * workflow *execution's* session is run by the server instead -- see
 * `useExecutionSessionChat`.) A FORBIDDEN (403) failure on the initial load
 * surfaces as the returned `forbidden` flag instead of an error toast.
 *
 * The chat is shared by every developer in the tenant, plus the background
 * generation run, so the history is re-fetched every {@link POLL_INTERVAL_MS}
 * and messages from other participants appear without a reload. Polling pauses
 * while the current viewer's own run is in flight and skips re-applying an
 * unchanged history -- see {@link historySignature} for what counts as
 * unchanged. The viewer's own run ends with the same re-read, which reconciles
 * the ids the live stream minted with the persisted ones without disturbing a
 * single bubble.
 *
 * Sender attribution rides on the same `/messages` response as the history, so
 * each message can show who sent it without a request of its own.
 *
 * @param workflowId - The workflow whose design session this is.
 * @param sessionId - The design session's ADK session id.
 * @param ownerUserId - The session's owner, whom unattributed messages (the
 *   background generation run's) fall back to.
 */
export function useDesignSessionChat(workflowId: string, sessionId: string, ownerUserId: string) {
  const parentId = workflowId;
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, isRunning, isStreaming, error, pendingRenderCalls, suggestions } =
    useAppSelector((s) => s.chat);
  // The session the mount effect has already initialized. React StrictMode (and
  // Fast Refresh) mount, unmount, then remount in development, re-invoking the
  // mount effect for the same session; guarding on this stops the repeat run
  // from calling setSession again and wiping what the first one loaded.
  const initializedSessionRef = useRef<string | null>(null);
  // Per-message sender attribution for the shared chat: a map from message id
  // to the sender's user id, and the resolved sender User records (always
  // including the owner, for the fallback below).
  const [messageSenders, setMessageSenders] = useState<Map<string, string>>(new Map());
  const [senderUsers, setSenderUsers] = useState<Map<string, User>>(new Map());
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
   * Apply the sender attribution a fetched history carries, and resolve the
   * User records it names.
   *
   * The sender map comes back on the history's own records, so it costs no
   * extra request; only the User records are fetched separately.
   */
  const applyAttribution = useCallback(
    async (history: SessionHistory) => {
      setMessageSenders(history.senders);
      // The owner is resolved too, even when they sent nothing: unattributed
      // messages fall back to them.
      setSenderUsers(await getUsersByIds([ownerUserId, ...history.senders.values()]));
    },
    [ownerUserId]
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
      const history = await getDesignSessionHistory(parentId);
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
      console.error("failed to refresh session history", err);
    }
  }, [parentId, sessionId, dispatch, applyAttribution]);

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
    async (content: string) => {
      if (!sessionId || isRunning) return;

      const msgId = crypto.randomUUID();
      dispatch(addUserMessage({ id: msgId, content }));
      locallySentIds.current.add(msgId);

      const agent = createDesignSessionAgent(parentId, sessionId);

      const pending = store.getState().chat.pendingRenderCalls;
      for (const ack of buildRenderAckMessages(pending)) {
        agent.addMessage(ack);
      }
      if (pending.length > 0) dispatch(clearPendingRenderCalls());

      agent.addMessage({ id: msgId, role: "user", content });

      try {
        await agent.runAgent(
          { tools: [RENDER_APPROVAL_TOOL] },
          makeEventHandlers(dispatch, (call) => {
            dispatch(addPendingRenderCall(call));
          })
        );
      } catch (err) {
        console.error("stream error", err);
        dispatch(setError("An error occurred while communicating with the agent."));
        return;
      }

      dispatch(finishRun());
      // Everything the run produced is now persisted with its sender and its
      // task association; re-read it all in one pass. The rendered bubbles keep
      // their keys, so reconciling their ids with the persisted ones is invisible.
      resyncAfterRun();
    },
    [parentId, sessionId, isRunning, dispatch, resyncAfterRun]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: store.getState is a stable reference; adding it would cause spurious re-runs
  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction, values: Record<string, unknown>) => {
      if (!sessionId || isRunning) return;

      dispatch(startRun());

      const agent = createDesignSessionAgent(parentId, sessionId);

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
        console.error("stream error", err);
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
    [parentId, sessionId, isRunning, dispatch, resyncAfterRun]
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: initialization runs once per session; the guard below keeps it from repeating
  useEffect(() => {
    // Initialize each session exactly once. A repeat run for the same session
    // (StrictMode/Fast Refresh remount) is a no-op; a genuine session change
    // re-initializes.
    if (initializedSessionRef.current === sessionId) return;
    initializedSessionRef.current = sessionId;
    appliedSignatureRef.current = null;
    reapplyAfterRunRef.current = false;
    setForbidden(false);
    dispatch(setSession(sessionId));
    getDesignSessionHistory(parentId, SUPPRESS_FORBIDDEN_TOAST)
      .then((history) => {
        const loadedMessages = history.messages;
        dispatch(resumeSession({ sessionId, messages: loadedMessages }));
        // Record the loaded history so the first poll doesn't re-apply it.
        appliedSignatureRef.current = historySignature(loadedMessages);
        // Catches its own failure, so the catch below only sees the history's.
        void applyAttribution(history).catch((err: unknown) => {
          console.error("failed to load session attribution", err);
        });
      })
      .catch((err: unknown) => {
        if (isForbiddenError(err)) setForbidden(true);
      });
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
    suggestions,
    sendMessage,
    sendA2uiAction,
    messageSenders,
    senderUsers,
    locallySentMessageIds: locallySentIds.current,
    forbidden,
  };
}
