"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { ActivityMessageBubble } from "./ActivityMessageBubble";
import { AssistantMessageBubble } from "./AssistantMessageBubble";
import { UserMessageBubble } from "./UserMessageBubble";

export function MessageBubble({
  message,
  isStreaming = false,
  onAction,
}: {
  message: Message;
  isStreaming?: boolean;
  onAction?: (action: A2UIUserAction) => void;
}) {
  if (message.role === "user") return <UserMessageBubble message={message} />;
  if (message.role === "assistant")
    return <AssistantMessageBubble message={message} isStreaming={isStreaming} />;
  if (message.role === "activity")
    return <ActivityMessageBubble message={message} onAction={onAction} />;
  return null;
}
