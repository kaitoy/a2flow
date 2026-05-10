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
      <div
        className={[
          "max-w-[75%] rounded-2xl rounded-tl-md px-4 py-2.5",
          "text-sm leading-relaxed whitespace-pre-wrap break-words",
          "glass-panel text-on-surface",
        ].join(" ")}
      >
        {textContent || (isStreaming ? null : " ")}
        {isStreaming && (
          <span className="inline-block w-[2px] h-[1em] ml-0.5 bg-accent align-middle animate-blink" />
        )}
      </div>
    </div>
  );
}
