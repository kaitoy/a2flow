'use client';

import type { Message } from '@/store/chatSlice';
import { type A2UIUserAction } from '@ag-ui/a2ui-middleware';
import { A2uiRenderer } from './A2uiRenderer';

export function MessageBubble({
  message,
  onAction,
}: {
  message: Message;
  onAction?: (action: A2UIUserAction) => void;
}) {
  const isUser = message.role === 'user';

  if (message.a2uiPayload != null) {
    return (
      <div className="flex justify-start mb-3">
        <div className="max-w-[85%]">
          <A2uiRenderer payload={JSON.parse(message.a2uiPayload!)} onAction={onAction} />
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-900 rounded-bl-sm'
        }`}
      >
        {message.content || (message.isStreaming ? null : '\u00a0')}
        {message.isStreaming && (
          <span className="inline-block w-[2px] h-[1em] ml-0.5 bg-current align-middle animate-blink" />
        )}
      </div>
    </div>
  );
}
