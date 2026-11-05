/**
 * @module WorkflowSessionPage — the workflow session: the LLM chat a workflow
 * execution runs in, the run-time counterpart of the design session.
 *
 * A workflow session has no record of its own; it exists one-to-one with its
 * WorkflowExecution, so the `[executionId]` route segment identifies it and the
 * page loads that execution to render the chat.
 */
"use client";

import { AlertTriangle } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatInput } from "@/components/ChatInput";
import { ConsultationNotice } from "@/components/ConsultationNotice";
import { ExecutionSessionTabs } from "@/components/ExecutionSessionTabs";
import { InitiatorResumeNotice } from "@/components/InitiatorResumeNotice";
import { MessageList } from "@/components/MessageList";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SidebarDrawer } from "@/components/ui/sidebar-drawer";
import { WorkflowSessionSkeleton } from "@/components/WorkflowSessionSkeleton";
import { WorkflowTaskTimeline } from "@/components/WorkflowTaskTimeline";
import { useExecutionSessionChat } from "@/hooks/useExecutionSessionChat";
import { useSessionSenderRenderer } from "@/hooks/useSessionSenderRenderer";
import { useT } from "@/i18n/provider";
import {
  type ExecutionSession,
  getWorkflowExecution,
  isForbiddenError,
  listExecutionSessions,
  SUPPRESS_FORBIDDEN_TOAST,
  startSessionConsultation,
  type WorkflowExecution,
} from "@/lib/api";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** How often (ms) to re-read the run's sessions, so new branches and status changes show. */
const SESSIONS_POLL_MS = 5_000;

/**
 * The run's sessions, re-read every {@link SESSIONS_POLL_MS}, and the one the
 * viewer is looking at — kept in the `?session=` query parameter so a link can
 * open a particular branch. Defaults to the main session.
 */
function useSessionSelection(execution: WorkflowExecution) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessions, setSessions] = useState<ExecutionSession[]>([]);
  const selected = searchParams.get("session") ?? execution.sessionId;

  useEffect(() => {
    let active = true;
    const load = () =>
      listExecutionSessions(execution.id)
        .then((list) => {
          if (active) setSessions(list);
        })
        .catch((err: unknown) => console.error("failed to list sessions", err));
    void load();
    const id = setInterval(load, SESSIONS_POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [execution.id]);

  const select = useCallback(
    (sessionId: string) => {
      const query = sessionId === execution.sessionId ? "" : `?session=${sessionId}`;
      router.replace(`/workflow-executions/${execution.id}/session${query}`);
    },
    [router, execution.id, execution.sessionId]
  );

  /** Show a session the server just returned, without waiting for the next poll. */
  const add = useCallback((session: ExecutionSession) => {
    setSessions((list) => [...list.filter((s) => s.id !== session.id), session]);
  }, []);
  return { sessions, selected, select, add };
}

/** Renders the chat UI for an already-loaded WorkflowExecution, including the task timeline and message list. */
function WorkflowSessionView({ execution }: { execution: WorkflowExecution }) {
  const t = useT();
  const dispatch = useAppDispatch();
  const currentUser = useAppSelector((s) => s.auth.user);
  const { sessions, selected, select, add } = useSessionSelection(execution);
  const {
    messages,
    isRunning,
    isStreaming,
    error,
    pendingRenderCalls,
    suggestions,
    sendMessage,
    sendA2uiAction,
    messageSenders,
    senderUsers,
    locallySentMessageIds,
    messageTasks,
    tasks,
    forbidden: chatForbidden,
  } = useExecutionSessionChat(execution.id, selected, execution.initiatorId);
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [timelineDrawerOpen, setTimelineDrawerOpen] = useState(false);
  // Focus state shared by the timeline and chat: a hovered entry wins over the
  // scroll-spy position so a deliberate hover always drives the highlight.
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null);
  const [scrolledTaskId, setScrolledTaskId] = useState<string | null>(null);
  const highlightedTaskId = hoveredTaskId ?? scrolledTaskId;

  // Task lookup for labelling the chat groups, a shared task-id -> ordinal map so
  // the timeline and chat badges match, and the in-progress task to highlight in
  // the timeline (the latest by createdAt when several are running — `tasks` is
  // already in createdAt order, so that's simply the last one).
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);
  const taskIndexById = useMemo(() => new Map(tasks.map((t, i) => [t.id, i + 1])), [tasks]);
  const activeTaskId = useMemo(() => {
    const running = tasks.filter((t) => t.status === "in_progress");
    return running.at(-1)?.id ?? null;
  }, [tasks]);

  /** Scroll the chat to the group that introduces the selected task. */
  const handleSelectTask = (taskId: string) => {
    document
      .getElementById(`wf-task-group-${taskId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Who sent each message: the workflow agent for its own messages, and the
  // resolved human (applicant or approver) for everything a person said or acted
  // on. Drives both the avatar beside the message and which side of the thread
  // it takes. Shared with the design session — see the hook.
  const { renderAvatar, isOwnMessage } = useSessionSenderRenderer({
    agentLabel: execution.name,
    ownerUserId: execution.initiatorId,
    messageSenders,
    senderUsers,
    locallySentMessageIds,
    currentUser,
  });

  // An approver shares the chat but only their approval is theirs to act on;
  // the forms the agent renders for the other steps belong to the initiator.
  // The backend rejects anyone else's submission, so this only keeps the UI honest.
  const canActOnSurfaces = currentUser?.id === execution.initiatorId;

  // The selected session, while it holds a task back for its initiator.
  const waitingForInitiator = sessions.find(
    (s) => s.id === selected && s.status === "waiting_for_initiator"
  );
  // While the selected session waits on an approval it takes no messages: a
  // question opens (or continues) its consultation, shown in a tab of its own.
  const awaitingApproval = sessions.some(
    (s) => s.id === selected && s.status === "waiting_for_approval"
  );
  const askInConsultation = useCallback(
    async (message: string) => {
      try {
        const consultation = await startSessionConsultation(execution.id, selected, message);
        add(consultation);
        select(consultation.id ?? selected);
      } catch (err) {
        // The error toast already explains it.
        console.error("failed to open a consultation", err);
      }
    },
    [execution.id, selected, add, select]
  );

  if (chatForbidden) {
    return <AccessDeniedState fill="screen" />;
  }

  return (
    <div className="flex h-dvh overflow-hidden">
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId={activeTaskId}
        taskIndexById={taskIndexById}
        highlightedTaskId={highlightedTaskId}
        onSelectTask={handleSelectTask}
        onHoverTask={setHoveredTaskId}
        collapsed={timelineCollapsed}
        onToggle={() => setTimelineCollapsed((c) => !c)}
        className="max-md:hidden"
      />
      <SidebarDrawer
        open={timelineDrawerOpen}
        onClose={() => setTimelineDrawerOpen(false)}
        label={t("workflowExecutions.workflowTasks2")}
      >
        <WorkflowTaskTimeline
          tasks={tasks}
          activeTaskId={activeTaskId}
          taskIndexById={taskIndexById}
          highlightedTaskId={highlightedTaskId}
          onSelectTask={(taskId) => {
            setTimelineDrawerOpen(false);
            handleSelectTask(taskId);
          }}
          collapsed={false}
          onToggle={() => setTimelineDrawerOpen(false)}
        />
      </SidebarDrawer>
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader onMenuClick={() => setTimelineDrawerOpen(true)} />

        <div className="shrink-0 px-4 pt-3 sm:px-6">
          <Breadcrumbs
            items={[
              { label: t("common.home"), href: "/" },
              { label: t("common.workflowExecutions"), href: "/workflow-executions" },
              // Links to this session's own execution record. Unlike the
              // (nullable) design-time workflow id, the execution id always
              // exists — even after its parent workflow design has been deleted.
              { label: execution.name, href: `/workflow-executions/${execution.id}` },
              { label: t("common.session") },
            ]}
          />
          <ExecutionSessionTabs
            sessions={sessions}
            mainSessionId={execution.sessionId}
            value={selected}
            onChange={select}
          />
        </div>

        {error && (
          <div className="shrink-0 mx-4 mt-3">
            <ErrorBanner error={error} onDismiss={() => dispatch(clearError())} />
          </div>
        )}

        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          isRunning={isRunning}
          renderAvatar={renderAvatar}
          isOwnMessage={isOwnMessage}
          messageTasks={messageTasks}
          tasksById={tasksById}
          taskIndexById={taskIndexById}
          highlightedTaskId={highlightedTaskId}
          onVisibleTaskChange={setScrolledTaskId}
          onHoverTask={setHoveredTaskId}
          onAction={sendA2uiAction}
          pendingRenderCalls={pendingRenderCalls}
          canActOnSurfaces={canActOnSurfaces}
        />
        {waitingForInitiator && !isRunning && (
          <div className="shrink-0 mx-4 mb-2">
            <InitiatorResumeNotice
              taskTitle={tasksById.get(waitingForInitiator.initiatorTaskId ?? "")?.title ?? null}
              canResume={canActOnSurfaces}
              onSend={sendMessage}
            />
          </div>
        )}
        {awaitingApproval && !isRunning && (
          <div className="shrink-0 mx-4 mb-2">
            <ConsultationNotice />
          </div>
        )}
        <ChatInput
          onSend={awaitingApproval ? askInConsultation : sendMessage}
          disabled={isRunning}
          allowAttachments={!awaitingApproval}
          suggestions={suggestions}
        />
      </div>
    </div>
  );
}

/** Full-screen error state shown when the WorkflowExecution record fails to load, with a retry action. */
function WorkflowSessionLoadError({ onRetry }: { onRetry: () => void }) {
  const t = useT();
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title={t("workflowExecutions.couldntLoadThisWorkflow")}
        description={t("workflowExecutions.somethingWentWrongWhileLoadingThisWorkflow")}
      />
      <Button variant="secondary" onClick={onRetry}>
        {t("common.retry")}
      </Button>
    </div>
  );
}

export default function WorkflowSessionPage() {
  const params = useParams<{ executionId: string }>();
  const executionId = params.executionId;
  const [workflowExecution, setWorkflowExecution] = useState<WorkflowExecution | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: retryCount is a bump counter that re-triggers the fetch, not a data dependency
  useEffect(() => {
    setLoadFailed(false);
    setForbidden(false);
    getWorkflowExecution(executionId, SUPPRESS_FORBIDDEN_TOAST)
      .then(setWorkflowExecution)
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        console.error("failed to load workflow execution", err);
        setLoadFailed(true);
      });
  }, [executionId, retryCount]);

  const retry = useCallback(() => setRetryCount((c) => c + 1), []);

  return (
    <AuthProvider>
      {workflowExecution ? (
        <WorkflowSessionView execution={workflowExecution} />
      ) : forbidden ? (
        <AccessDeniedState fill="screen" />
      ) : loadFailed ? (
        <WorkflowSessionLoadError onRetry={retry} />
      ) : (
        <WorkflowSessionSkeleton />
      )}
    </AuthProvider>
  );
}
