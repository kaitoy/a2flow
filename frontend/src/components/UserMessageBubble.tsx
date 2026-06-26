"use client";

import type { TextInputContent, UserMessage } from "@ag-ui/core";
import type { ReactNode } from "react";

/** Extract the plain text from a user message, handling both string and content-part array forms. */
function getUserTextContent(content: UserMessage["content"]): string {
  return typeof content === "string"
    ? content
    : content
        .filter((c): c is TextInputContent => c.type === "text")
        .map((c) => c.text)
        .join("");
}

/**
 * Render a user message as a right-aligned gradient bubble.
 *
 * When `avatar` is provided (workflow sessions, where several people share the
 * chat) it is shown on the outer (right) edge so the sender is identifiable;
 * without it the layout is unchanged for the single-user chat.
 */
export function UserMessageBubble({
  message,
  avatar,
}: {
  message: UserMessage;
  avatar?: ReactNode;
}) {
  const textContent = getUserTextContent(message.content);
  const rowClass = avatar
    ? "flex justify-end items-end gap-2 mb-3 animate-message-in"
    : "flex justify-end mb-3 animate-message-in";
  return (
    <div className={rowClass}>
      <div
        className={[
          "max-w-[75%] rounded-2xl rounded-tr-md px-4 py-2.5",
          "text-sm leading-relaxed whitespace-pre-wrap break-words",
          "bg-gradient-to-br from-accent to-secondary text-on-primary",
          "shadow-[0_8px_24px_-12px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.35)]",
        ].join(" ")}
      >
        {textContent || " "}
      </div>
      {avatar}
    </div>
  );
}
