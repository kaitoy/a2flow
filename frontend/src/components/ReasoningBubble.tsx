"use client";

import type { ReasoningActivityContent } from "@/lib/agentActivity";

/**
 * Render the agent's streamed reasoning ("thinking") text as a subtle,
 * left-aligned panel, visually distinct from a normal assistant reply.
 * Renders nothing until some reasoning text has arrived. While `isThinking`
 * (the agent is still actively reasoning and hasn't started a reply yet),
 * the panel carries the signature live edge.
 */
export function ReasoningBubble({
  content,
  isThinking = false,
}: {
  content: ReasoningActivityContent;
  isThinking?: boolean;
}) {
  const text = content.text ?? "";
  if (!text) return null;
  return (
    <div className="mb-3 flex justify-start animate-message-in">
      <div
        className={[
          "max-w-[75%] rounded-2xl rounded-tl-md border border-dashed border-glass-border px-4 py-2.5",
          "text-xs leading-relaxed whitespace-pre-wrap break-words italic",
          "bg-glass text-on-surface-variant",
          isThinking ? "live-edge" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <div className="mb-1 flex items-center gap-1.5 text-[11px] not-italic tracking-wide uppercase">
          <span aria-hidden>💭</span>
          <span>Thinking</span>
        </div>
        {text}
      </div>
    </div>
  );
}
