"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { AgentSubscriber, HttpAgent } from "@ag-ui/client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "react-redux";
import { formatActionContent, type PendingRenderCall } from "@/lib/a2uiAction";
import { createAgentSubscriber } from "@/lib/agentSubscriber";
import {
  createSessionStreamAgent,
  getExecutionSessionHistory,
  getUsersByIds,
  isForbiddenError,
  listWorkflowTasks,
  type SessionHistory,
  SUPPRESS_FORBIDDEN_TOAST,
  sendSessionInput,
  type User,
  uploadSessionFile,
  type WorkflowTask,
} from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
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

/** How long to wait before re-subscribing after a stream fails, in ms. */
const RETRY_DELAY_MS = 2_000;

/**
 * Map a session's streamed AG-UI events to Redux, including the events that
 * mark a turn starting and the approval controls a `render_approval` call shows.
 */
function makeSubscriber(
  dispatch: AppDispatch,
  onRenderA2uiEnd: (call: PendingRenderCall) => void
): AgentSubscriber {
  return {
    ...createAgentSubscriber(dispatch, {
      onRenderA2uiEnd: (toolCallId, args) => {
        const surfaceId = typeof args.surfaceId === "string" ? args.surfaceId : null;
        onRenderA2uiEnd({ toolCallId, surfaceId });
      },
      onRenderApprovalEnd: (toolCallId, args) => {
        // The decision is made with PATCH /approvals and resumes the run on the
        // server; the controls only need drawing here.
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
    }),
    onRunStartedEvent: async () => {
      dispatch(startRun());
    },
  };
}

/** Wait `ms` milliseconds, or less if `signal` aborts first. */
function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/**
 * Follow and take part in one session of a workflow execution.
 *
 * The server runs every turn of a workflow session -- its kickoff, a resumption
 * after an approval, and whatever someone sends -- so the browser never drives
 * the agent. It reads the session's history, then subscribes to its stream
 * from the history's cursor: every viewer sees each turn live, whoever started
 * it. When a turn ends the stream closes, and the hook re-reads the history
 * (which by then carries the turn's sender and task attribution) and
 * subscribes again for the next one.
 *
 * Sending is queuing: {@link sendMessage} and {@link sendA2uiAction} post input
 * the server runs as the next turn. Files are uploaded first, so an abandoned
 * draft leaves nothing behind, and the message names them so the transcript
 * still shows what was attached. Approvals are decided in their own controls
 * (`PATCH /approvals`), never here.
 *
 * A FORBIDDEN (403) failure on the first history load surfaces as `forbidden`
 * instead of an error toast, so the page can render its access-denied state.
 *
 * @param executionId - The WorkflowExecution the session belongs to.
 * @param sessionId - The ADK session to follow.
 * @param initiatorId - The run's initiator, whom unattributed messages fall
 *   back to.
 */
export function useExecutionSessionChat(
  executionId: string,
  sessionId: string,
  initiatorId: string
) {
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { messages, isRunning, isStreaming, error, pendingRenderCalls, suggestions } =
    useAppSelector((s) => s.chat);
  const [messageSenders, setMessageSenders] = useState<Map<string, string>>(new Map());
  const [senderUsers, setSenderUsers] = useState<Map<string, User>>(new Map());
  const [messageTasks, setMessageTasks] = useState<Map<string, string>>(new Map());
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [forbidden, setForbidden] = useState(false);
  // Ids of messages this viewer sent: their optimistic ids differ from the
  // persisted ones until the next history read replaces them.
  const locallySentIds = useRef<Set<string>>(new Set());

  /** Apply the sender and task attribution a history read carries. */
  const applyAttribution = useCallback(
    async (history: SessionHistory) => {
      setMessageSenders(history.senders);
      setMessageTasks(history.tasks);
      const [users, taskList] = await Promise.all([
        getUsersByIds([initiatorId, ...history.senders.values()]),
        listWorkflowTasks(executionId),
      ]);
      setSenderUsers(users);
      setTasks(taskList);
    },
    [executionId, initiatorId]
  );

  useEffect(() => {
    const controller = new AbortController();
    let agent: HttpAgent | null = null;
    dispatch(setSession(sessionId));
    setForbidden(false);

    /** Read the history and return the cursor to stream from, or null to stop. */
    const read = async (initial: boolean): Promise<number | null> => {
      try {
        const history = await getExecutionSessionHistory(
          executionId,
          sessionId,
          initial ? SUPPRESS_FORBIDDEN_TOAST : undefined
        );
        if (controller.signal.aborted) return null;
        dispatch(
          initial
            ? resumeSession({ sessionId, messages: history.messages })
            : syncPolledMessages({ sessionId, messages: history.messages })
        );
        // Both reducers clear isRunning; a queued or running turn shows the
        // agent working now rather than once its first event streams in.
        if (history.running) dispatch(startRun());
        void applyAttribution(history).catch((err: unknown) => {
          console.error("failed to load session attribution", err);
        });
        return history.streamCursor;
      } catch (err) {
        if (initial && isForbiddenError(err)) {
          setForbidden(true);
          return null;
        }
        console.error("failed to load session history", err);
        return controller.signal.aborted ? null : 0;
      }
    };

    void (async () => {
      let cursor = await read(true);
      while (cursor !== null && !controller.signal.aborted) {
        agent = createSessionStreamAgent(executionId, sessionId, cursor);
        try {
          await agent.runAgent(
            {},
            makeSubscriber(dispatch, (call) => dispatch(addPendingRenderCall(call)))
          );
        } catch (err) {
          if (controller.signal.aborted) return;
          console.error("session stream failed", err);
          await delay(RETRY_DELAY_MS, controller.signal);
        }
        if (controller.signal.aborted) return;
        dispatch(finishRun());
        cursor = await read(false);
      }
    })();

    return () => {
      controller.abort();
      agent?.abortRun();
    };
  }, [executionId, sessionId, dispatch, applyAttribution]);

  /** Queue a chat message, uploading its attachments first. */
  const sendMessage = useCallback(
    async (prompt: string, files: File[] = []) => {
      let content = prompt;
      try {
        if (files.length > 0) {
          const uploaded = await Promise.all(
            files.map((file) => uploadSessionFile(executionId, file))
          );
          // The stored names, which may be numbered variants of the picked ones.
          const names = uploaded.map((file) => file.name).join(", ");
          content = `${prompt}\n\nAttached files: ${names}`.trim();
        }
      } catch (err) {
        console.error("failed to upload session files", err);
        dispatch(setError("The files could not be attached. Nothing was sent."));
        return;
      }
      const id = crypto.randomUUID();
      dispatch(addUserMessage({ id, content }));
      locallySentIds.current.add(id);
      dispatch(startRun());
      try {
        await sendSessionInput(executionId, sessionId, { message: content });
      } catch (err) {
        // The error toast already explains it (a turn is under way, or an
        // approval is pending); the message is dropped on the next read.
        console.error("failed to send the message", err);
        dispatch(finishRun());
      }
    },
    [executionId, sessionId, dispatch]
  );

  /**
   * Queue the answer to a form the agent rendered: the action taken and the
   * values entered, as the result of the `render_a2ui` call that drew it.
   */
  const sendA2uiAction = useCallback(
    async (action: A2UIUserAction, values: Record<string, unknown>) => {
      const pending = store.getState().chat.pendingRenderCalls;
      const target =
        pending.findLast((call) => call.surfaceId === action.surfaceId) ?? pending.at(-1);
      if (!target) return;
      dispatch(clearPendingRenderCalls());
      dispatch(startRun());
      try {
        await sendSessionInput(executionId, sessionId, {
          a2uiAction: {
            toolCallId: target.toolCallId,
            content: formatActionContent(action, values),
          },
        });
      } catch (err) {
        console.error("failed to submit the form", err);
        dispatch(finishRun());
      }
    },
    [executionId, sessionId, dispatch, store]
  );

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
    messageTasks,
    tasks,
    forbidden,
  };
}
