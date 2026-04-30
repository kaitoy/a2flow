'use client';

import { useChat } from '@/hooks/useChat';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { SessionList } from './SessionList';
import { clearError } from '@/store/chatSlice';
import { useAppSelector } from '@/store/hooks';
import { useAppDispatch } from '@/store/hooks';

export function Chat({ sessionId: initialSessionId }: { sessionId: string }) {
  const dispatch = useAppDispatch();
  const userId = useAppSelector((s) => s.chat.userId);
  const { messages, sessionId, isRunning, isStreaming, error, sendMessage, sendA2uiAction, switchSession, newSession } = useChat(initialSessionId);

  return (
    <div className="flex h-screen bg-white">
      <SessionList
        userId={userId}
        currentSessionId={sessionId}
        onSelect={switchSession}
        onNew={newSession}
        disabled={isRunning}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="shrink-0 border-b border-gray-200 px-6 py-3">
          <h1 className="text-base font-semibold text-gray-900">A2Flow</h1>
        </header>

        {error && (
          <div className="shrink-0 flex items-center justify-between bg-red-50 border-b border-red-200 px-6 py-2 text-sm text-red-600">
            <span>{error}</span>
            <button
              onClick={() => dispatch(clearError())}
              className="ml-4 text-red-400 hover:text-red-600"
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
