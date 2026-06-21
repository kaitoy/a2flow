"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { animated, useSpring } from "@react-spring/web";
import { Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";
import { TOOL_CALL_ACTIVITY_TYPE, type ToolCallActivityContent } from "@/lib/agentActivity";
import { useMotionConfig } from "@/lib/motion";
import { MessageBubble } from "./MessageBubble";
import { EmptyState } from "./ui/empty-state";

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
  onAction,
  onApprovalResolved,
}: {
  messages: Message[];
  isStreaming?: boolean;
  isRunning?: boolean;
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
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isStreaming={isStreaming && i === messages.length - 1}
            onAction={onAction}
            onApprovalResolved={onApprovalResolved}
          />
        ))}
        {shouldShowWorkingIndicator(messages, isRunning, isStreaming) && <WorkingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
