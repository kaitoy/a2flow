'use client';

import { useChat } from '@/hooks/useChat';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { clearError } from '@/store/chatSlice';
import { useAppDispatch } from '@/store/hooks';

export function Chat() {
  const dispatch = useAppDispatch();
  const { messages, isRunning, error, sendMessage, sendA2uiAction } = useChat();

  return (
    <div className="flex flex-col h-screen bg-white">
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

      <MessageList messages={messages} onAction={sendA2uiAction} />
      <ChatInput onSend={sendMessage} disabled={isRunning} />
    </div>
  );
}
