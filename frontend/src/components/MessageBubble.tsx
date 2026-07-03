"use client";

import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import type { ReactNode } from "react";
import { ActivityMessageBubble } from "./ActivityMessageBubble";
import { AssistantMessageBubble } from "./AssistantMessageBubble";
import { UserMessageBubble } from "./UserMessageBubble";

/**
 * Dispatch a message to the appropriate role-specific bubble component.
 *
 * `avatar` is an optional sender avatar shown beside conversational (`user` /
 * `assistant`) bubbles in workflow sessions. It is also forwarded to
 * `ActivityMessageBubble`, which shows it only next to a resolved A2UI
 * surface (the user who acted on it); other activity types ignore it.
 */
export function MessageBubble({
  message,
  isStreaming = false,
  avatar,
  onAction,
  onApprovalResolved,
}: {
  message: Message;
  isStreaming?: boolean;
  avatar?: ReactNode;
  onAction?: (action: A2UIUserAction) => void;
  onApprovalResolved?: (toolCallId: string, decision: "approved" | "rejected") => void;
}) {
  if (message.role === "user") return <UserMessageBubble message={message} avatar={avatar} />;
  if (message.role === "assistant")
    return <AssistantMessageBubble message={message} isStreaming={isStreaming} avatar={avatar} />;
  if (message.role === "activity")
    return (
      <ActivityMessageBubble
        message={message}
        avatar={avatar}
        onAction={onAction}
        onApprovalResolved={onApprovalResolved}
      />
    );
  return null;
}
