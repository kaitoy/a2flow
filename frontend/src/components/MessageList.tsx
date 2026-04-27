'use client';

import { useEffect, useRef } from 'react';
import type { Message } from '@/store/chatSlice';
import { type A2UIUserAction } from '@ag-ui/a2ui-middleware';
import { MessageBubble } from './MessageBubble';

export function MessageList({
  messages,
  onAction,
}: {
  messages: Message[];
  onAction?: (action: A2UIUserAction) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      {messages.length === 0 && (
        <div className="flex items-center justify-center h-full text-gray-400 text-sm select-none">
          Start a conversation
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onAction={onAction} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
