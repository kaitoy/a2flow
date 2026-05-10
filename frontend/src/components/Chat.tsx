"use client";

import { useChat } from "@/hooks/useChat";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { SessionList } from "./SessionList";
import { ThemeToggle } from "./ThemeToggle";

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
    <div className="flex h-screen overflow-hidden">
      <SessionList
        userId={userId}
        currentSessionId={sessionId}
        onSelect={switchSession}
        onNew={newSession}
        disabled={isRunning}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="shrink-0 flex items-center justify-between px-6 py-3 border-b border-glass-border bg-glass backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow animate-pulse" />
            <h1 className="text-[18px] leading-[28px] font-semibold tracking-tight text-gradient-accent">
              A2Flow
            </h1>
          </div>
          <ThemeToggle />
        </header>

        {error && (
          <div className="shrink-0 mx-4 mt-3 flex items-center justify-between gap-3 rounded-xl border border-error/40 bg-error-container px-4 py-2 text-sm text-on-error-container backdrop-blur-md">
            <span className="flex items-center gap-2">
              <span aria-hidden="true">⚠</span>
              {error}
            </span>
            <button
              type="button"
              onClick={() => dispatch(clearError())}
              className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-colors hover:bg-error/15 hover:text-on-error-container"
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
