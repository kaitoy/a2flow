"use client";

import type { AssistantMessage } from "@ag-ui/core";

export function AssistantMessageBubble({
  message,
  isStreaming = false,
}: {
  message: AssistantMessage;
  isStreaming?: boolean;
}) {
  const textContent = message.content ?? "";
  if (!textContent && !isStreaming) return null;
  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[75%] px-4 py-2.5 rounded text-sm leading-relaxed whitespace-pre-wrap break-words bg-surface-container border border-outline-variant text-on-surface">
        {textContent || (isStreaming ? null : " ")}
        {isStreaming && (
          <span className="inline-block w-[2px] h-[1em] ml-0.5 bg-current align-middle animate-blink" />
        )}
      </div>
    </div>
  );
}
