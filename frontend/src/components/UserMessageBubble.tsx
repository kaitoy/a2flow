"use client";

import type { TextInputContent, UserMessage } from "@ag-ui/core";

function getUserTextContent(content: UserMessage["content"]): string {
  return typeof content === "string"
    ? content
    : content
        .filter((c): c is TextInputContent => c.type === "text")
        .map((c) => c.text)
        .join("");
}

export function UserMessageBubble({ message }: { message: UserMessage }) {
  const textContent = getUserTextContent(message.content);
  return (
    <div className="flex justify-end mb-3">
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
    </div>
  );
}
