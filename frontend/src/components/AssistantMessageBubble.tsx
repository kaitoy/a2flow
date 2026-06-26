"use client";

import type { AssistantMessage } from "@ag-ui/core";
import type { ReactNode } from "react";

/**
 * Render an assistant message as a left-aligned glass bubble with an optional streaming cursor.
 *
 * When `avatar` is provided (workflow sessions) it is shown on the outer (left)
 * edge to mark the message as the agent's; without it the layout is unchanged
 * for the single-user chat.
 */
export function AssistantMessageBubble({
  message,
  isStreaming = false,
  avatar,
}: {
  message: AssistantMessage;
  isStreaming?: boolean;
  avatar?: ReactNode;
}) {
  const textContent = message.content ?? "";
  if (!textContent && !isStreaming) return null;
  const rowClass = avatar
    ? "flex justify-start items-end gap-2 mb-3 animate-message-in"
    : "flex justify-start mb-3 animate-message-in";
  return (
    <div className={rowClass}>
      {avatar}
      <div
        className={[
          "max-w-[75%] rounded-2xl rounded-tl-md px-4 py-2.5",
          "text-sm leading-relaxed whitespace-pre-wrap break-words",
          "glass-panel text-on-surface",
        ].join(" ")}
      >
        {textContent || (isStreaming ? null : " ")}
        {isStreaming && (
          <span
            className={[
              "inline-block w-[2px] h-[1em] ml-0.5 align-middle origin-center rounded-full",
              "bg-gradient-to-b from-accent to-secondary shadow-[0_0_8px_var(--color-accent-soft)]",
              "animate-blink motion-safe:animate-pulse-cursor",
            ].join(" ")}
          />
        )}
      </div>
    </div>
  );
}
