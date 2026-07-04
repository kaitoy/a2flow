"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { animated, useSpring } from "@react-spring/web";
import { Sparkles } from "lucide-react";
import { Fragment, type ReactNode, type UIEvent, useEffect, useMemo, useRef } from "react";
import { TOOL_CALL_ACTIVITY_TYPE, type ToolCallActivityContent } from "@/lib/agentActivity";
import type { WorkflowTask } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
import { MessageBubble } from "./MessageBubble";
import { EmptyState } from "./ui/empty-state";
import { WorkflowTaskGroup } from "./WorkflowTaskGroup";

/**
 * A run of consecutive messages that share the same workflow task (or no task).
 * `taskId` is `null` for ungrouped messages (the opening prompt or unassigned
 * messages); `anchorId` is set only on the first run of each task so scroll
 * anchors stay unique.
 */
interface MessageRun {
  taskId: string | null;
  anchorId?: string;
  messages: Message[];
}

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
        <span>Agent is thinking…</span>
      </div>
    </div>
  );
}

/**
 * Scrollable list of chat messages. New messages follow to the bottom only when
 * the viewer is already near the bottom, so an incoming message (for example one
 * polled in from another workflow participant) never yanks a reader away from
 * earlier history they're scrolled up to read.
 */
export function MessageList({
  messages,
  isStreaming = false,
  isRunning = false,
  renderAvatar,
  messageTasks,
  tasksById,
  taskIndexById,
  highlightedTaskId = null,
  onVisibleTaskChange,
  onHoverTask,
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
   * sessions) each run of consecutive same-task messages is wrapped in a
   * {@link WorkflowTaskGroup} so the task's boundary is visible.
   */
  messageTasks?: Map<string, string>;
  /** Optional WorkflowTask id -> task lookup, used to label the task groups. */
  tasksById?: Map<string, WorkflowTask>;
  /** Optional WorkflowTask id -> 1-based ordinal, shared with the timeline badges. */
  taskIndexById?: Map<string, number>;
  /** Id of the task to emphasize (driven by timeline hover / scroll-spy). */
  highlightedTaskId?: string | null;
  /** Called as the user scrolls with the task id occupying the top of the viewport (scroll-spy). */
  onVisibleTaskChange?: (taskId: string | null) => void;
  /** Called with a task id when a group is hovered, and `null` on leave. */
  onHoverTask?: (taskId: string | null) => void;
  onAction?: (action: A2UIUserAction) => void;
  onApprovalResolved?: (toolCallId: string, decision: "approved" | "rejected") => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Whether the viewer is parked near the bottom. Updated on scroll *before* the
  // next content append, so the scroll effect can decide whether to follow.
  const stickToBottomRef = useRef(true);
  const emptyConfig = useMotionConfig("gentle");
  const emptyStateSpring = useSpring({
    from: { opacity: 0, transform: "scale(0.92)" },
    to: { opacity: 1, transform: "scale(1)" },
    config: emptyConfig,
  });

  // Group the flat message list into runs of consecutive same-task messages.
  // Only the first run of each task carries a scroll anchor so DOM ids stay
  // unique; messages with no task form anchorless, rail-less runs.
  const runs = useMemo<MessageRun[]>(() => {
    const result: MessageRun[] = [];
    const seen = new Set<string>();
    let current: MessageRun | null = null;
    // One ADK event expands into several store messages, but `messageTasks` is
    // keyed by the ADK event id, so the derived ones — synthesized A2UI /
    // approval / MCP activity bubbles, reasoning and tool messages — carry
    // generated ids absent from the map. Once a task is under way the backend
    // assigns every later event to the current task, so an unmapped message is
    // always a continuation of it: carry the last resolved task forward instead
    // of falling back to `null`, which would eject the bubble (e.g. an A2UI
    // surface) from its group and split the run into duplicate headings. Only
    // the initial pre-task planning messages stay `null` and ungrouped.
    let lastTaskId: string | null = null;
    for (const msg of messages) {
      const taskId: string | null = messageTasks?.get(msg.id) ?? lastTaskId;
      lastTaskId = taskId;
      if (!current || current.taskId !== taskId) {
        let anchorId: string | undefined;
        if (taskId && !seen.has(taskId)) {
          anchorId = `wf-task-group-${taskId}`;
          seen.add(taskId);
        }
        current = { taskId, anchorId, messages: [] };
        result.push(current);
      }
      current.messages.push(msg);
    }
    return result;
  }, [messages, messageTasks]);

  const lastMessageId = messages[messages.length - 1]?.id;

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll to bottom whenever messages change
  useEffect(() => {
    if (stickToBottomRef.current) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** Track whether the viewer is near the bottom so new messages only follow then. */
  const handleScroll = (e: UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  // Scroll-spy: report which task group sits at the top of the viewport so the
  // timeline can follow the scroll. Rebuilt whenever the set of groups changes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `runs` re-runs the effect so the new section nodes get observed
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || !onVisibleTaskChange) return;
    const sections = Array.from(root.querySelectorAll<HTMLElement>("[data-task-id]"));
    if (sections.length === 0) return;

    let lastReported: string | null = null;
    const recompute = () => {
      const rootRect = root.getBoundingClientRect();
      // The "active" group is the last one whose top has scrolled above a line
      // 30% down from the top of the viewport.
      const lineY = rootRect.top + rootRect.height * 0.3;
      let active: string | null = null;
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= lineY) {
          active = section.dataset.taskId ?? null;
        }
      }
      if (active !== lastReported) {
        lastReported = active;
        onVisibleTaskChange(active);
      }
    };

    const observer = new IntersectionObserver(recompute, {
      root,
      rootMargin: "0px 0px -70% 0px",
      threshold: 0,
    });
    for (const section of sections) observer.observe(section);
    return () => observer.disconnect();
  }, [runs, onVisibleTaskChange]);

  /** Render a message bubble, marking the global last message as streaming. */
  const renderBubble = (msg: Message): ReactNode => (
    <MessageBubble
      key={msg.id}
      message={msg}
      isStreaming={isStreaming && msg.id === lastMessageId}
      avatar={renderAvatar?.(msg)}
      onAction={onAction}
      onApprovalResolved={onApprovalResolved}
    />
  );

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-6">
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
        {runs.map((run) => {
          const key = run.messages[0]?.id ?? run.anchorId;
          if (!run.taskId) {
            return <Fragment key={key}>{run.messages.map(renderBubble)}</Fragment>;
          }
          return (
            <WorkflowTaskGroup
              key={key}
              task={tasksById?.get(run.taskId)}
              index={taskIndexById?.get(run.taskId) ?? 0}
              anchorId={run.anchorId}
              isHighlighted={highlightedTaskId === run.taskId}
              onHover={(id) => onHoverTask?.(id)}
            >
              {run.messages.map(renderBubble)}
            </WorkflowTaskGroup>
          );
        })}
        {shouldShowWorkingIndicator(messages, isRunning, isStreaming) && <WorkingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
