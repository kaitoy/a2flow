"use client";

import { useChat } from "@/hooks/useChat";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { SessionList } from "./SessionList";

export function Chat({ sessionId: initialSessionId }: { sessionId: string }) {
  const dispatch = useAppDispatch();
  const userId = useAppSelector((s) => s.chat.userId);
  const {
    messages,
    sessionId,
    isRunning,
    isStreaming,
    error,
    sendMessage,
    sendA2uiAction,
    switchSession,
    newSession,
  } = useChat(initialSessionId);

  return (
    <div className="flex h-screen bg-surface">
      <SessionList
        userId={userId}
        currentSessionId={sessionId}
        onSelect={switchSession}
        onNew={newSession}
        disabled={isRunning}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="shrink-0 border-b border-outline-variant px-6 py-3">
          <h1 className="text-[18px] leading-[28px] font-semibold text-on-surface tracking-[-0.01em]">
            A2Flow
          </h1>
        </header>

        {error && (
          <div className="shrink-0 flex items-center justify-between bg-error-container border-b border-2 border-error px-6 py-2 text-sm text-on-error-container">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => dispatch(clearError())}
              className="ml-4 text-on-error-container/60 hover:text-on-error-container"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        <MessageList messages={messages} isStreaming={isStreaming} onAction={sendA2uiAction} />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}
