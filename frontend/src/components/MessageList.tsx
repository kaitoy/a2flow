"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";

/** Scrollable list of chat messages that auto-scrolls to the bottom when new messages arrive. */
export function MessageList({
  messages,
  isStreaming = false,
  onAction,
}: {
  messages: Message[];
  isStreaming?: boolean;
  onAction?: (action: A2UIUserAction) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-3xl flex-col">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center py-20 text-center select-none">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl glass-panel-strong shadow-glow">
              <span className="text-2xl">✦</span>
            </div>
            <h2 className="mb-1 text-2xl font-semibold tracking-tight text-gradient-accent">
              Start a conversation
            </h2>
            <p className="text-sm text-on-surface-variant">
              Ask anything, build an A2UI surface, or kick off a workflow.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isStreaming={isStreaming && i === messages.length - 1}
            onAction={onAction}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
