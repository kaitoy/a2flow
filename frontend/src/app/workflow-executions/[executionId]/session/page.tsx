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
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatInput } from "@/components/ChatInput";
import { MessageList } from "@/components/MessageList";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SidebarDrawer } from "@/components/ui/sidebar-drawer";
import { WorkflowSessionSkeleton } from "@/components/WorkflowSessionSkeleton";
import { WorkflowTaskTimeline } from "@/components/WorkflowTaskTimeline";
import { useSessionAvatarRenderer } from "@/hooks/useSessionAvatarRenderer";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import {
  getWorkflowExecution,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  type WorkflowExecution,
} from "@/lib/api";
import logger from "@/lib/logger";
import { EXECUTION_KICKOFF_PROMPT } from "@/lib/workflowKickoff";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** Renders the chat UI for an already-loaded WorkflowExecution, including the task timeline and message list. */
function WorkflowSessionView({ execution }: { execution: WorkflowExecution }) {
  const dispatch = useAppDispatch();
  const currentUser = useAppSelector((s) => s.auth.user);
  const {
    messages,
    isRunning,
    isStreaming,
    error,
    pendingRenderCalls,
    sendMessage,
    sendA2uiAction,
    sendApprovalResult,
    messageSenders,
    senderUsers,
    locallySentMessageIds,
    messageTasks,
    tasks,
    forbidden: chatForbidden,
  } = useWorkflowSessionChat(
    execution.id,
    execution.sessionId,
    EXECUTION_KICKOFF_PROMPT,
    execution.initiatorId
  );
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [timelineDrawerOpen, setTimelineDrawerOpen] = useState(false);
  // Focus state shared by the timeline and chat: a hovered entry wins over the
  // scroll-spy position so a deliberate hover always drives the highlight.
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null);
  const [scrolledTaskId, setScrolledTaskId] = useState<string | null>(null);
  const highlightedTaskId = hoveredTaskId ?? scrolledTaskId;

  // Task lookup for labelling the chat groups, a shared task-id -> ordinal map so
  // the timeline and chat badges match, and the in-progress task to highlight in
  // the timeline (the latest by position when several are running).
  const tasksById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);
  const taskIndexById = useMemo(() => new Map(tasks.map((t, i) => [t.id, i + 1])), [tasks]);
  const activeTaskId = useMemo(() => {
    const running = tasks.filter((t) => t.status === "in_progress");
    if (running.length === 0) return null;
    return running.reduce((a, b) => ((b.position ?? 0) >= (a.position ?? 0) ? b : a)).id;
  }, [tasks]);

  /** Scroll the chat to the group that introduces the selected task. */
  const handleSelectTask = (taskId: string) => {
    document
      .getElementById(`wf-task-group-${taskId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // The sender avatar shown beside each message: the workflow agent for its own
  // messages, and the resolved human (applicant or approver) for everything a
  // person said or acted on. Shared with the design session — see the hook.
  const renderAvatar = useSessionAvatarRenderer({
    agentLabel: execution.name,
    ownerUserId: execution.initiatorId,
    messageSenders,
    senderUsers,
    locallySentMessageIds,
    currentUser,
  });

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
        label="Workflow tasks"
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
              { label: "Admin", href: "/admin" },
              { label: "Workflow Executions", href: "/admin/workflow-executions" },
              // Links to this session's own execution record. Unlike the
              // (nullable) design-time workflow id, the execution id always
              // exists — even after its parent workflow design has been deleted.
              { label: execution.name, href: `/admin/workflow-executions/${execution.id}` },
              { label: "Session" },
            ]}
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
          messageTasks={messageTasks}
          tasksById={tasksById}
          taskIndexById={taskIndexById}
          highlightedTaskId={highlightedTaskId}
          onVisibleTaskChange={setScrolledTaskId}
          onHoverTask={setHoveredTaskId}
          onAction={sendA2uiAction}
          onApprovalResolved={sendApprovalResult}
          pendingRenderCalls={pendingRenderCalls}
        />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}

/** Full-screen error state shown when the WorkflowExecution record fails to load, with a retry action. */
function WorkflowSessionLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title="Couldn't load this workflow"
        description="Something went wrong while loading this workflow execution."
      />
      <Button variant="secondary" onClick={onRetry}>
        Retry
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
        logger.error(err, "failed to load workflow execution");
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
