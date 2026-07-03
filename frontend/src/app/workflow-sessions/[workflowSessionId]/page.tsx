/** @module WorkflowSessionPage — Loads a WorkflowSession record and renders the workflow chat view. */
"use client";

import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { useParams } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { AgentAvatar } from "@/components/AgentAvatar";
import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatErrorBanner } from "@/components/ChatErrorBanner";
import { ChatInput } from "@/components/ChatInput";
import { MessageList } from "@/components/MessageList";
import { Avatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { WorkflowTaskTimeline } from "@/components/WorkflowTaskTimeline";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import { A2UI_SOURCE_TOOL_CALL_ID_KEY } from "@/lib/agentActivity";
import { formatUserName, getWorkflowSession, type User, type WorkflowSession } from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function WorkflowSessionView({ ws }: { ws: WorkflowSession }) {
  const dispatch = useAppDispatch();
  const currentUser = useAppSelector((s) => s.auth.user);
  const {
    messages,
    isRunning,
    isStreaming,
    error,
    sendMessage,
    sendA2uiAction,
    sendApprovalResult,
    messageSenders,
    senderUsers,
    locallySentMessageIds,
    messageTasks,
    tasks,
  } = useWorkflowSessionChat(ws.id, ws.sessionId, ws.workflowPrompt, ws.userId);
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
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

  /** Render a tooltip-wrapped avatar for the given (possibly unresolved) user. */
  const userAvatar = (user: User | null): ReactNode => (
    <Tooltip label={user ? formatUserName(user) : "Unknown sender"}>
      <span className="inline-flex">
        <Avatar user={user} size={28} />
      </span>
    </Tooltip>
  );

  /**
   * Render the sender avatar shown beside a message: the workflow agent for its
   * own (`assistant`) messages, the resolved human (applicant or approver) for
   * `user` messages, and — once resolved — the human who acted on a rendered
   * A2UI surface or decided an approval request. Messages whose sender is
   * unknown fall back to the session owner; messages the current viewer just
   * sent are attributed to them until the persisted, attributed history
   * reloads. A2UI surfaces and approval controls show no avatar until someone
   * has actually resolved them.
   */
  const renderAvatar = (message: Message): ReactNode => {
    if (message.role === "assistant") {
      return (
        <Tooltip label={ws.workflowName}>
          <span className="inline-flex">
            <AgentAvatar size={28} />
          </span>
        </Tooltip>
      );
    }
    if (message.role === "user") {
      const senderId = messageSenders.get(message.id);
      let user: User | null;
      if (senderId) {
        user = senderUsers.get(senderId) ?? null;
      } else if (locallySentMessageIds.has(message.id)) {
        user = currentUser;
      } else {
        user = senderUsers.get(ws.userId) ?? null;
      }
      return userAvatar(user);
    }
    if (message.role === "activity" && message.activityType === A2UIActivityType) {
      const toolCallId = message.content[A2UI_SOURCE_TOOL_CALL_ID_KEY];
      const senderId = typeof toolCallId === "string" ? messageSenders.get(toolCallId) : undefined;
      if (!senderId) return null;
      return userAvatar(senderUsers.get(senderId) ?? null);
    }
    if (message.role === "activity" && message.activityType === APPROVAL_ACTIVITY_TYPE) {
      // An approval activity's id is the render_approval tool call id, which is
      // also the key the decision's tool result is attributed under — so the
      // sender lookup resolves to the user who approved or rejected.
      const senderId = messageSenders.get(message.id);
      if (!senderId) return null;
      return userAvatar(senderUsers.get(senderId) ?? null);
    }
    return null;
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId={activeTaskId}
        taskIndexById={taskIndexById}
        highlightedTaskId={highlightedTaskId}
        onSelectTask={handleSelectTask}
        onHoverTask={setHoveredTaskId}
        collapsed={timelineCollapsed}
        onToggle={() => setTimelineCollapsed((c) => !c)}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader>
          <span className="h-6 w-px shrink-0 bg-glass-border" aria-hidden="true" />
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-accent shadow-glow animate-pulse" />
          <span className="truncate text-[18px] leading-[28px] font-semibold tracking-tight text-gradient-accent">
            {ws.workflowName}
          </span>
        </AppHeader>

        <ChatErrorBanner error={error} onDismiss={() => dispatch(clearError())} />

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
        />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}

/**
 * Placeholder chat layout shown while the WorkflowSession record loads, so the
 * page presents the header shell and a few message-bubble skeletons instead of
 * flashing a blank screen.
 */
function WorkflowSessionSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="flex h-screen overflow-hidden">
      <div className="flex w-[260px] shrink-0 flex-col gap-3 border-r border-glass-border bg-glass px-4 py-4 backdrop-blur-xl">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-9 w-full rounded-xl" />
        <Skeleton className="h-9 w-full rounded-xl" />
        <Skeleton className="h-9 w-full rounded-xl" />
      </div>
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader>
          <span className="h-6 w-px shrink-0 bg-glass-border" aria-hidden="true" />
          <Skeleton className="h-5 w-40" />
        </AppHeader>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-4">
            <Skeleton className="ml-auto h-16 w-2/3 rounded-2xl rounded-tr-md" />
            <Skeleton className="h-24 w-3/4 rounded-2xl rounded-tl-md" />
            <Skeleton className="ml-auto h-12 w-1/2 rounded-2xl rounded-tr-md" />
            <Skeleton className="h-20 w-2/3 rounded-2xl rounded-tl-md" />
          </div>
        </div>

        <div className="shrink-0 px-6 pb-6">
          <Skeleton className="mx-auto h-14 w-full max-w-3xl rounded-2xl" />
        </div>
      </div>
    </div>
  );
}

export default function WorkflowSessionPage() {
  const params = useParams<{ workflowSessionId: string }>();
  const workflowSessionId = params.workflowSessionId;
  const [workflowSession, setWorkflowSession] = useState<WorkflowSession | null>(null);

  useEffect(() => {
    getWorkflowSession(workflowSessionId)
      .then(setWorkflowSession)
      .catch(() => {});
  }, [workflowSessionId]);

  return (
    <AuthProvider>
      {workflowSession ? <WorkflowSessionView ws={workflowSession} /> : <WorkflowSessionSkeleton />}
    </AuthProvider>
  );
}
