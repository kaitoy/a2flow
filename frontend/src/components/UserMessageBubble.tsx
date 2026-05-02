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
      <div className="max-w-[75%] px-4 py-2.5 rounded text-sm leading-relaxed whitespace-pre-wrap break-words bg-primary-container text-on-primary-container">
        {textContent || " "}
      </div>
    </div>
  );
}
