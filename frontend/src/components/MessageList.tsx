"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import { contentToText, type Message } from "@ag-ui/core";
import { animated, useSpring } from "@react-spring/web";
import { ArrowDown, Sparkles } from "lucide-react";
import {
  Fragment,
  type ReactNode,
  type UIEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useT } from "@/i18n/provider";
import type { PendingRenderCall } from "@/lib/a2uiAction";
import {
  REASONING_ACTIVITY_TYPE,
  type ReasoningActivityContent,
  TOOL_CALL_ACTIVITY_TYPE,
  type ToolCallActivityContent,
} from "@/lib/agentActivity";
import type { WorkflowTask } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
import type { RenderedMessage } from "@/store/chatSlice";
import { ELICITATION_ACTIVITY_TYPE } from "./ElicitationControls";
import { MessageBubble } from "./MessageBubble";
import { Button } from "./ui/button";
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
  messages: RenderedMessage[];
}

/**
 * The React key a message's bubble is rendered under.
 *
 * A message the viewer has already watched appear keeps the key it first got,
 * even once a poll replaces its id with the persisted one — see
 * `RenderedMessage` for why the two can differ and what remounting costs.
 */
function renderKeyOf(message: RenderedMessage | undefined): string | undefined {
  return message?.renderKey ?? message?.id;
}

/**
 * Whether the agent is working but has nothing on screen yet — true when a run
 * is in progress, no text is streaming, and the latest message is not already a
 * running tool line (which shows its own spinner), a live reasoning panel
 * (which carries its own "thinking" affordance via the live edge), or an MCP
 * server's still-open question (the turn is waiting on the person, not the
 * agent; once the stream re-sends it with a `status`, the agent is back at work).
 */
function shouldShowWorkingIndicator(
  messages: Message[],
  isRunning: boolean,
  isStreaming: boolean
): boolean {
  if (!isRunning || isStreaming) return false;
  const last = messages[messages.length - 1];
  if (last?.role === "activity") {
    if (
      last.activityType === TOOL_CALL_ACTIVITY_TYPE &&
      (last.content as unknown as ToolCallActivityContent).status === "running"
    ) {
      return false;
    }
    if (
      last.activityType === ELICITATION_ACTIVITY_TYPE &&
      !(last.content as { status?: string }).status
    ) {
      return false;
    }
    if (
      last.activityType === REASONING_ACTIVITY_TYPE &&
      (last.content as unknown as ReasoningActivityContent).text
    ) {
      return false;
    }
  }
  return true;
}

/** Whether a scroll container is scrolled to within 120px of its bottom. */
function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
}

/**
 * Subtle "agent is thinking" pulse shown at the bottom of the list while a run
 * is in flight and no other surface (streaming text, a running tool line, a
 * live reasoning panel) is already covering that signal. Since it only ever
 * renders while genuinely live, it carries the signature live edge unconditionally.
 */
function WorkingIndicator() {
  const t = useT();
  return (
    <div className="mb-3 flex justify-start animate-message-in" aria-live="polite">
      <div className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs glass-panel text-on-surface-variant live-edge">
        <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow animate-pulse" />
        <span>{t("app.agentIsThinking")}</span>
      </div>
    </div>
  );
}

/**
 * Scrollable list of chat messages.
 *
 * When a run starts while the viewer is near the bottom, the list scrolls once
 * so the latest message (usually the prompt just sent) sits at the top of the
 * viewport, with a trailing spacer reserving a screenful of empty room below
 * it. The reply streams into that room and the list does not scroll again for
 * the rest of the run — even once the reply outgrows the room — so text already
 * on screen never drifts while it is being read. The spacer shrinks as content
 * fills it and stays until the next run, since removing it would clamp the
 * scroll position and make the view jump.
 *
 * When a message is added, or a run finishes, with the end of the messages out
 * of sight below the viewport — a reply that outgrew its room, or a message that
 * arrived while the viewer was scrolled up — a "New messages below" button
 * floats over the bottom of the list until the viewer scrolls down to the end.
 * Clicking it jumps there and follows the reply for the rest of the run.
 *
 * Outside a run, new messages follow to the bottom only when the viewer is
 * already near the bottom, so an incoming message (for example one polled in
 * from another workflow participant) never yanks a reader away from earlier
 * history they're scrolled up to read. The same following also covers content
 * that grows *after* `messages` itself last changed — an A2UI surface that
 * finishes mounting a beat after its activity bubble appears, or an approval
 * control that swaps in its resolved state once its fetch lands — tracked via a
 * `ResizeObserver` on the message column rather than the `messages` prop alone.
 */
export function MessageList({
  messages,
  isStreaming = false,
  isRunning = false,
  renderAvatar,
  isOwnMessage,
  messageTasks,
  tasksById,
  taskIndexById,
  highlightedTaskId = null,
  onVisibleTaskChange,
  onHoverTask,
  onAction,
  onApprovalResolved,
  pendingRenderCalls,
  canActOnSurfaces,
}: {
  messages: RenderedMessage[];
  isStreaming?: boolean;
  isRunning?: boolean;
  /**
   * Optional sender-avatar renderer. When provided (workflow executions) the
   * returned node is shown beside each conversational bubble; omitted for the
   * single-user chat, which renders no avatars.
   */
  renderAvatar?: (message: Message) => ReactNode;
  /**
   * Optional predicate saying whether the signed-in viewer sent a message.
   * Provided alongside `renderAvatar` by the session chats, where it puts the
   * viewer's own bubbles and surfaces on the right and everyone else's on the
   * left. Omitted for the single-user chat, whose every user message is the
   * viewer's own — hence the `true` default below.
   */
  isOwnMessage?: (message: Message) => boolean;
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
  onAction?: (action: A2UIUserAction, values: Record<string, unknown>) => void;
  onApprovalResolved?: (toolCallId: string, decision: "approved" | "rejected" | "returned") => void;
  /**
   * `render_a2ui` calls still awaiting an acknowledging tool result. Drives
   * which A2UI surfaces render as answered (locked and pre-filled) versus
   * still interactive — see the `pendingToolCallIds`/`toolResultContentByCallId`
   * derivation below.
   */
  pendingRenderCalls?: PendingRenderCall[];
  /**
   * Whether the signed-in viewer may submit the still-pending A2UI surfaces.
   * The workflow session passes `false` for everyone but the run's initiator,
   * which renders those surfaces inert with a waiting note; omitted (true) for
   * the single-user chat and the design session.
   */
  canActOnSurfaces?: boolean;
}) {
  const t = useT();
  const scrollRef = useRef<HTMLDivElement>(null);
  // Wraps the message column itself (unlike scrollRef, which is clipped by
  // overflow-y-auto and never resizes) so the ResizeObserver below sees the
  // column's real height, including content that grows after mount.
  const contentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Whether the viewer is parked near the bottom. Updated on scroll *before* the
  // next content append, so the scroll effect can decide whether to follow.
  const stickToBottomRef = useRef(true);
  // Trailing room below the message column that a run's reply streams into.
  const spacerRef = useRef<HTMLDivElement>(null);
  // The message scrolled to the top when the current (or last) run started;
  // the spacer is sized so it can stay there.
  const anchorElRef = useRef<HTMLElement | null>(null);
  // True for the duration of a run that scrolled to its anchor: no following.
  const anchoredRef = useRef(false);
  const prevIsRunningRef = useRef(false);
  // Content has landed below the viewport that the viewer hasn't scrolled to.
  const [hasUnseenBelow, setHasUnseenBelow] = useState(false);
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
    // the initial pre-task design messages stay `null` and ungrouped.
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

  // Ids of render_a2ui calls still awaiting an answer, and the raw content of
  // every tool-result message keyed by the call it answers (present in
  // `messages` — see synthesizeActivityMessages — but never rendered directly).
  // ActivityMessageBubble uses these to lock and pre-fill already-answered A2UI
  // surfaces so they can never be resubmitted.
  const pendingToolCallIds = useMemo(
    () => new Set((pendingRenderCalls ?? []).map((call) => call.toolCallId)),
    [pendingRenderCalls]
  );
  const toolResultContentByCallId = useMemo(() => {
    const map = new Map<string, string>();
    for (const msg of messages) {
      if (msg.role === "tool" && msg.toolCallId)
        map.set(msg.toolCallId, contentToText(msg.content));
    }
    return map;
  }, [messages]);

  const lastMessageId = messages[messages.length - 1]?.id;

  /** Whether the end of the messages lies below the bottom edge of the viewport. */
  const isEndBelowView = useCallback(() => {
    const scrollEl = scrollRef.current;
    const bottom = bottomRef.current;
    if (!scrollEl || !bottom) return false;
    return bottom.getBoundingClientRect().top > scrollEl.getBoundingClientRect().bottom + 1;
  }, []);

  /**
   * Follow to the bottom, but only while the viewer is already parked there and
   * no run is filling its reserved room. `nearest` leaves the view alone while
   * the end of the content is still on screen above a leftover spacer.
   */
  const scrollToBottomIfStuck = useCallback(() => {
    if (anchoredRef.current || !stickToBottomRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  /**
   * Jump to the end of the messages (the "New messages below" button) and keep
   * following it for the rest of the current run.
   */
  const scrollToEnd = () => {
    anchoredRef.current = false;
    stickToBottomRef.current = true;
    setHasUnseenBelow(false);
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  };

  /**
   * Size the spacer so the anchor message can sit at the top of the viewport:
   * a viewport's height minus the content already below the anchor's top.
   */
  const updateSpacer = useCallback(() => {
    const scrollEl = scrollRef.current;
    const spacer = spacerRef.current;
    const bottom = bottomRef.current;
    if (!scrollEl || !spacer || !bottom) return;
    const anchor = anchorElRef.current;
    let height = 0;
    if (anchor?.isConnected) {
      const style = getComputedStyle(scrollEl);
      const room =
        scrollEl.clientHeight -
        (Number.parseFloat(style.paddingTop) || 0) -
        (Number.parseFloat(style.paddingBottom) || 0);
      const used = bottom.getBoundingClientRect().top - anchor.getBoundingClientRect().top;
      height = Math.max(0, room - used);
    }
    spacer.style.height = `${height}px`;
  }, []);

  /**
   * Show the "New messages below" button if the list is not following and the
   * end of the messages is out of sight. Called only when a message is added or
   * a run finishes — not as a reply merely grows, nor on a resize — so the
   * button means "something new arrived", not "there is more to scroll".
   */
  const flagIfUnseen = useCallback(() => {
    if (!anchoredRef.current && stickToBottomRef.current) return;
    if (anchoredRef.current) {
      // While the reply still has room, its end is (or is about to be, once
      // the anchoring scroll lands) on screen.
      updateSpacer();
      if (Number.parseFloat(spacerRef.current?.style.height ?? "") > 0) return;
    }
    if (isEndBelowView()) setHasUnseenBelow(true);
  }, [isEndBelowView, updateSpacer]);

  const prevMessageCountRef = useRef(messages.length);
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll to bottom whenever messages change
  useEffect(() => {
    scrollToBottomIfStuck();
    if (messages.length > prevMessageCountRef.current) flagIfUnseen();
    prevMessageCountRef.current = messages.length;
  }, [messages]);

  // Whether the latest message is a prompt the viewer just sent themselves.
  const lastMessage = messages[messages.length - 1];
  const lastSentByViewer = lastMessage?.role === "user" && (isOwnMessage?.(lastMessage) ?? true);

  // When a run starts, scroll the latest message to the top in one go and
  // reserve the room below it for the reply. Always done for the viewer's own
  // prompt — wherever they were scrolled to, e.g. still partway up the previous
  // reply that ran past the screen. Otherwise skipped for a viewer scrolled up
  // into the history: in a workflow session a run can start on someone else's
  // message, or on A2Flow's own, and must not pull a reader away.
  useLayoutEffect(() => {
    const wasRunning = prevIsRunningRef.current;
    prevIsRunningRef.current = isRunning;
    if (!isRunning) {
      // The reply grew without a scroll event, so the last reading of
      // stickToBottomRef predates it. Re-measure, or a reply that ran past the
      // screen would be followed to the bottom the moment the run ends.
      if (anchoredRef.current && scrollRef.current) {
        stickToBottomRef.current = isNearBottom(scrollRef.current);
      }
      anchoredRef.current = false;
      if (wasRunning) flagIfUnseen();
      return;
    }
    if (wasRunning || !(stickToBottomRef.current || lastSentByViewer)) return;
    // The last message that renders something: a `tool` message renders
    // nothing, leaving an empty wrapper.
    const wrappers = contentRef.current?.querySelectorAll<HTMLElement>("[data-message-key]") ?? [];
    let anchor: HTMLElement | null = null;
    for (let i = wrappers.length - 1; i >= 0; i--) {
      if (wrappers[i].childElementCount > 0) {
        anchor = wrappers[i];
        break;
      }
    }
    if (!anchor) return;
    anchorElRef.current = anchor;
    anchoredRef.current = true;
    updateSpacer();
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [isRunning, lastSentByViewer, updateSpacer, flagIfUnseen]);

  // Content can grow after `messages` last changed — an A2UI surface finishes
  // mounting a beat after its activity bubble appears, an approval control
  // swaps in its resolved state once its fetch lands — so watch the actual
  // layout height rather than relying on `messages` alone to know when to follow.
  // The scroll container is watched too, so a window resize re-sizes the spacer.
  useEffect(() => {
    const content = contentRef.current;
    const scrollEl = scrollRef.current;
    if (!content || !scrollEl) return;
    const observer = new ResizeObserver(() => {
      updateSpacer();
      scrollToBottomIfStuck();
    });
    observer.observe(content);
    observer.observe(scrollEl);
    return () => observer.disconnect();
  }, [scrollToBottomIfStuck, updateSpacer]);

  /** Track whether the viewer is near the bottom so new messages only follow then. */
  const handleScroll = (e: UIEvent<HTMLDivElement>) => {
    stickToBottomRef.current = isNearBottom(e.currentTarget);
    if (!isEndBelowView()) setHasUnseenBelow(false);
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
    // The trailing sentinel (bottomRef) is a zero-height marker pinned at the
    // end of the messages (only the run spacer follows it), so it enters the
    // viewport once the viewer has scrolled to the last of the content. That's
    // the only reliable way to know the last group is "active": its own top may never
    // cross the 30% line below if there isn't enough trailing content to push
    // it there (e.g. a short final task with no WorkingIndicator after it).
    let atBottom = false;
    const recompute = () => {
      if (atBottom) {
        const active = sections[sections.length - 1].dataset.taskId ?? null;
        if (active !== lastReported) {
          lastReported = active;
          onVisibleTaskChange(active);
        }
        return;
      }
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

    const sectionObserver = new IntersectionObserver(recompute, {
      root,
      rootMargin: "0px 0px -70% 0px",
      threshold: 0,
    });
    for (const section of sections) sectionObserver.observe(section);

    const bottomObserver = new IntersectionObserver(
      ([entry]) => {
        atBottom = entry.isIntersecting;
        recompute();
      },
      { root, threshold: 0 }
    );
    if (bottomRef.current) bottomObserver.observe(bottomRef.current);

    return () => {
      sectionObserver.disconnect();
      bottomObserver.disconnect();
    };
  }, [runs, onVisibleTaskChange]);

  /**
   * Render a message bubble, marking the global last message as streaming (or,
   * absent a text stream, as still-thinking so a trailing reasoning panel gets
   * the live edge). The wrapper is what a run's scroll anchors to.
   */
  const renderBubble = (msg: RenderedMessage): ReactNode => (
    <div key={renderKeyOf(msg)} data-message-key={renderKeyOf(msg)}>
      <MessageBubble
        message={msg}
        isStreaming={isStreaming && msg.id === lastMessageId}
        isThinking={isRunning && !isStreaming && msg.id === lastMessageId}
        avatar={renderAvatar?.(msg)}
        isOwn={isOwnMessage?.(msg) ?? true}
        onAction={onAction}
        onApprovalResolved={onApprovalResolved}
        pendingToolCallIds={pendingToolCallIds}
        toolResultContentByCallId={toolResultContentByCallId}
        canActOnSurfaces={canActOnSurfaces}
      />
    </div>
  );

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scroll-py-6 px-4 py-6"
      >
        <div ref={contentRef} className="mx-auto flex max-w-3xl flex-col">
          {messages.length === 0 && (
            <animated.div style={emptyStateSpring}>
              <EmptyState
                icon={Sparkles}
                animation="breathe"
                title={t("app.startAConversation")}
                description={t("app.askAnythingBuildAnA2uiSurfaceOr")}
              />
            </animated.div>
          )}
          {runs.map((run) => {
            // Prefer the task's stable anchorId over the run's leading message id:
            // messageTasks refreshes independently of messages, so the message
            // that happens to lead a task's run can change between renders even
            // though the task itself hasn't — keying on messages[0] there would
            // remount the whole group (e.g. an in-progress ApprovalControls).
            const key = run.anchorId ?? renderKeyOf(run.messages[0]);
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
        <div ref={spacerRef} aria-hidden />
      </div>
      <div
        aria-live="polite"
        className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center"
      >
        {hasUnseenBelow && (
          <Button
            variant="secondary"
            onClick={scrollToEnd}
            className="pointer-events-auto gap-1.5 animate-message-in"
          >
            <ArrowDown className="size-4" aria-hidden />
            {t("app.newMessagesBelow")}
          </Button>
        )}
      </div>
    </div>
  );
}
