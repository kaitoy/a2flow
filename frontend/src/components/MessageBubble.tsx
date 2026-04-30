'use client';

import type { Message, TextInputContent } from '@ag-ui/core';
import { A2UIActivityType, A2UI_OPERATIONS_KEY, type A2UIUserAction } from '@ag-ui/a2ui-middleware';
import { A2uiRenderer } from './A2uiRenderer';

function getTextContent(message: Message): string {
  if (message.role === 'user') {
    return typeof message.content === 'string'
      ? message.content
      : message.content.filter((c): c is TextInputContent => c.type === 'text').map((c) => c.text).join('');
  }
  if (message.role === 'assistant') return message.content ?? '';
  return '';
}

export function MessageBubble({
  message,
  isStreaming = false,
  onAction,
}: {
  message: Message;
  isStreaming?: boolean;
  onAction?: (action: A2UIUserAction) => void;
}) {
  if (message.role === 'activity') {
    if (message.activityType !== A2UIActivityType) return null;
    return (
      <div className="flex justify-start mb-3">
        <div className="max-w-[85%]">
          <A2uiRenderer payload={message.content[A2UI_OPERATIONS_KEY]} onAction={onAction} />
        </div>
      </div>
    );
  }

  if (message.role !== 'user' && message.role !== 'assistant') return null;

  const isUser = message.role === 'user';
  const textContent = getTextContent(message);

  if (!isUser && !textContent && !isStreaming) return null;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-900 rounded-bl-sm'
        }`}
      >
        {textContent || (isStreaming ? null : '\u00a0')}
        {isStreaming && (
          <span className="inline-block w-[2px] h-[1em] ml-0.5 bg-current align-middle animate-blink" />
        )}
      </div>
    </div>
  );
}
