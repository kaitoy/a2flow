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
 * Render a user message as a chat bubble on the sender's side of the thread.
 *
 * The viewer's own messages sit on the right in the accent gradient; in a shared
 * session chat (workflow executions and design sessions, where several people
 * post into one conversation) another participant's message sits on the left
 * instead, in a secondary tint that keeps it distinct from the agent's colorless
 * glass bubble beside it.
 *
 * When `avatar` is provided the sender's avatar is shown on the bubble's outer
 * edge — right for the viewer, left for everyone else. Without it (the
 * single-user chat, which has only one possible sender) the layout is unchanged:
 * always right-aligned, no avatar.
 */
export function UserMessageBubble({
  message,
  avatar,
  isOwn = true,
}: {
  message: UserMessage;
  avatar?: ReactNode;
  /** Whether the signed-in viewer sent this message. Drives which side it takes. */
  isOwn?: boolean;
}) {
  const textContent = getUserTextContent(message.content);
  // Only a shared chat (one that identifies its senders) can place a message on
  // the left; without an avatar there is no other sender to distinguish.
  const onOwnSide = isOwn || !avatar;
  const rowClass = [
    "flex mb-3 animate-message-in",
    onOwnSide ? "justify-end" : "justify-start",
    avatar ? "items-end gap-2" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={rowClass}>
      {!onOwnSide && avatar}
      <div
        className={[
          "max-w-[75%] rounded-2xl px-4 py-2.5",
          "text-sm leading-relaxed whitespace-pre-wrap break-words",
          onOwnSide
            ? [
                avatar ? "rounded-br-md" : "rounded-tr-md",
                "bg-gradient-to-br from-accent to-secondary text-on-primary",
                "shadow-[0_8px_24px_-12px_var(--color-accent-soft),inset_0_1px_0_var(--inner-top-highlight)]",
              ].join(" ")
            : "rounded-bl-md bg-secondary/12 border border-secondary/25 text-on-surface",
        ].join(" ")}
      >
        {textContent || " "}
      </div>
      {onOwnSide && avatar}
    </div>
  );
}
