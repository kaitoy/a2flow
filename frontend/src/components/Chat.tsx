"use client";

import { useChat } from "@/hooks/useChat";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";

/**
 * Conversation panel for a single session: message list and input. The persistent
 * shell (sidebar, header, error banner) lives in the route layout, so this component
 * is the only part that re-mounts when navigating between sessions.
 */
export function Chat({ sessionId: initialSessionId }: { sessionId: string | null }) {
  const { messages, isRunning, isStreaming, pendingRenderCalls, sendMessage, sendA2uiAction } =
    useChat(initialSessionId);

  return (
    <>
      <MessageList
        messages={messages}
        isStreaming={isStreaming}
        isRunning={isRunning}
        onAction={sendA2uiAction}
        pendingRenderCalls={pendingRenderCalls}
      />
      <ChatInput onSend={sendMessage} disabled={isRunning} />
    </>
  );
}
