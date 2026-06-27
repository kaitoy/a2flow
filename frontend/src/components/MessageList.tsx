"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { animated, useSpring } from "@react-spring/web";
import { Sparkles } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useMemo, useRef } from "react";
import { TOOL_CALL_ACTIVITY_TYPE, type ToolCallActivityContent } from "@/lib/agentActivity";
import type { WorkflowTask } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
import { MessageBubble } from "./MessageBubble";
import { EmptyState } from "./ui/empty-state";
import { WorkflowTaskDivider } from "./WorkflowTaskDivider";

/**
 * Whether the agent is working but has nothing on screen yet — true when a run
 * is in progress, no text is streaming, and the latest message is not already a
 * running tool line (which shows its own spinner).
 */
function shouldShowWorkingIndicator(
  messages: Message[],
  isRunning: boolean,
  isStreaming: boolean
): boolean {
  if (!isRunning || isStreaming) return false;
  const last = messages[messages.length - 1];
  if (
    last?.role === "activity" &&
    last.activityType === TOOL_CALL_ACTIVITY_TYPE &&
    (last.content as unknown as ToolCallActivityContent).status === "running"
  ) {
    return false;
  }
  return true;
}

/** Subtle "agent is thinking" pulse shown at the bottom of the list while a run is in flight. */
function WorkingIndicator() {
  return (
    <div className="mb-3 flex justify-start animate-message-in" aria-live="polite">
      <div className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs glass-panel text-on-surface-variant">
        <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow animate-pulse" />
        <span>エージェントが考えています…</span>
      </div>
    </div>
  );
}

/** Scrollable list of chat messages that auto-scrolls to the bottom when new messages arrive. */
export function MessageList({
  messages,
  isStreaming = false,
  isRunning = false,
  renderAvatar,
  messageTasks,
  tasksById,
  onAction,
  onApprovalResolved,
}: {
  messages: Message[];
  isStreaming?: boolean;
  isRunning?: boolean;
  /**
   * Optional sender-avatar renderer. When provided (workflow sessions) the
   * returned node is shown beside each conversational bubble; omitted for the
   * single-user chat, which renders no avatars.
   */
  renderAvatar?: (message: Message) => ReactNode;
  /**
   * Optional message id -> WorkflowTask id map. When provided (workflow
   * sessions) a {@link WorkflowTaskDivider} is inserted wherever the active task
   * changes, grouping the messages below it under that task.
   */
  messageTasks?: Map<string, string>;
  /** Optional WorkflowTask id -> task lookup, used to label the dividers. */
  tasksById?: Map<string, WorkflowTask>;
  onAction?: (action: A2UIUserAction) => void;
  onApprovalResolved?: (toolCallId: string, decision: "approved" | "rejected") => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const emptyConfig = useMotionConfig("gentle");
  const emptyStateSpring = useSpring({
    from: { opacity: 0, transform: "scale(0.92)" },
    to: { opacity: 1, transform: "scale(1)" },
    config: emptyConfig,
  });

  // For each message, the task divider (if any) to render immediately before it.
  // A divider appears wherever the active task changes; only the first divider
  // for a given task carries a scroll anchor so its DOM id stays unique.
  const taskBoundaries = useMemo<Array<{ taskId: string; isFirst: boolean } | null>>(() => {
    if (!messageTasks) return messages.map(() => null);
    const seen = new Set<string>();
    let prev: string | null = null;
    return messages.map((msg) => {
      const taskId = messageTasks.get(msg.id) ?? null;
      let boundary: { taskId: string; isFirst: boolean } | null = null;
      if (taskId && taskId !== prev) {
        boundary = { taskId, isFirst: !seen.has(taskId) };
        seen.add(taskId);
      }
      if (taskId) prev = taskId;
      return boundary;
    });
  }, [messages, messageTasks]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-3xl flex-col">
        {messages.length === 0 && (
          <animated.div style={emptyStateSpring}>
            <EmptyState
              icon={Sparkles}
              animation="breathe"
              title="Start a conversation"
              description="Ask anything, build an A2UI surface, or kick off a workflow."
            />
          </animated.div>
        )}
        {messages.map((msg, i) => {
          const boundary = taskBoundaries[i];
          return (
            <Fragment key={msg.id}>
              {boundary && (
                <WorkflowTaskDivider
                  task={tasksById?.get(boundary.taskId)}
                  anchorId={boundary.isFirst ? `wf-task-divider-${boundary.taskId}` : undefined}
                />
              )}
              <MessageBubble
                message={msg}
                isStreaming={isStreaming && i === messages.length - 1}
                avatar={renderAvatar?.(msg)}
                onAction={onAction}
                onApprovalResolved={onApprovalResolved}
              />
            </Fragment>
          );
        })}
        {shouldShowWorkingIndicator(messages, isRunning, isStreaming) && <WorkingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
