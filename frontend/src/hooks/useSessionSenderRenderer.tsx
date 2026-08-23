"use client";

import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { type ReactNode, useCallback, useMemo } from "react";
import { AgentAvatar } from "@/components/AgentAvatar";
import { Avatar } from "@/components/ui/avatar";
import { Tooltip } from "@/components/ui/tooltip";
import { A2UI_SOURCE_TOOL_CALL_ID_KEY } from "@/lib/agentActivity";
import { formatUserName, type User } from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";

/** Inputs for {@link useSessionSenderRenderer}. */
export interface SessionSenderRendererOptions {
  /** Tooltip label for the agent's own avatar — the execution or workflow name. */
  agentLabel: string;
  /**
   * Fallback sender for messages with no recorded attribution: a workflow
   * session's `initiatorId`, a design session's `createdBy`. The chat is keyed
   * by this user, so history written before attribution existed (or by the
   * unattended background design run) is theirs by default.
   */
  ownerUserId: string;
  /** Message id (or tool call id) → sender user id, from `useWorkflowSessionChat`. */
  messageSenders: Map<string, string>;
  /** Resolved `User` records for every sender id above, plus the owner. */
  senderUsers: Map<string, User>;
  /** Ids of messages this viewer sent in this session, before the history reloads. */
  locallySentMessageIds: Set<string>;
  /** The signed-in user, used to attribute their own just-sent messages. */
  currentUser: User | null;
}

/** What {@link useSessionSenderRenderer} returns — see the hook for the resolution rules. */
export interface SessionSenderRenderer {
  /** The sender avatar to show beside a message, or `null` when nobody is attributed. */
  renderAvatar: (message: Message) => ReactNode;
  /** Whether the signed-in viewer is the message's sender, which drives its side of the chat. */
  isOwnMessage: (message: Message) => boolean;
}

/**
 * Resolve who sent each message in a session chat, as both an avatar and an
 * "is this mine?" predicate.
 *
 * Shared by both session chats — a workflow session and a design session are
 * each one ADK conversation several people post into, so both need the same
 * sender resolution:
 *
 * - `assistant` messages are the agent's: they get its glyph, tooltipped with
 *   `agentLabel`, and are never the viewer's own.
 * - `user` messages resolve through the attribution map, then through the ids
 *   this viewer just sent (their optimistic client ids differ from the persisted
 *   ADK event ids, so they are absent from the map until a reload), then fall
 *   back to the session's owner.
 * - A2UI surfaces resolve by the tool call id that produced them, and approval
 *   controls by their own id (which *is* the `render_approval` tool call id), so
 *   the sender is whoever acted on them. Both resolve to nobody until someone has.
 *
 * @param options - See {@link SessionSenderRendererOptions}.
 * @returns Stable callbacks mapping a message to its avatar and to its ownership.
 */
export function useSessionSenderRenderer({
  agentLabel,
  ownerUserId,
  messageSenders,
  senderUsers,
  locallySentMessageIds,
  currentUser,
}: SessionSenderRendererOptions): SessionSenderRenderer {
  /**
   * The user id credited with a message, or `null` when nobody is — the agent's
   * own messages, and surfaces nobody has acted on yet.
   */
  const resolveSenderId = useCallback(
    (message: Message): string | null => {
      if (message.role === "user") {
        const senderId = messageSenders.get(message.id);
        if (senderId) return senderId;
        if (locallySentMessageIds.has(message.id)) return currentUser?.id ?? null;
        return ownerUserId;
      }
      if (message.role === "activity" && message.activityType === A2UIActivityType) {
        const toolCallId = message.content[A2UI_SOURCE_TOOL_CALL_ID_KEY];
        return (
          (typeof toolCallId === "string" ? messageSenders.get(toolCallId) : undefined) ?? null
        );
      }
      if (message.role === "activity" && message.activityType === APPROVAL_ACTIVITY_TYPE) {
        // An approval activity's id is the render_approval tool call id, which is
        // also the key the decision's tool result is attributed under — so the
        // sender lookup resolves to the user who approved or rejected.
        return messageSenders.get(message.id) ?? null;
      }
      return null;
    },
    [ownerUserId, messageSenders, locallySentMessageIds, currentUser]
  );

  const renderAvatar = useCallback(
    (message: Message): ReactNode => {
      /** Render a tooltip-wrapped avatar for the given (possibly unresolved) user. */
      const userAvatar = (user: User | null): ReactNode => (
        <Tooltip label={user ? formatUserName(user) : "Unknown sender"}>
          <span className="inline-flex">
            <Avatar user={user} size={28} />
          </span>
        </Tooltip>
      );

      if (message.role === "assistant") {
        return (
          <Tooltip label={agentLabel}>
            <span className="inline-flex">
              <AgentAvatar size={28} />
            </span>
          </Tooltip>
        );
      }
      const senderId = resolveSenderId(message);
      if (message.role === "user") {
        // A user message always names a sender, even an unresolvable one — the
        // viewer's own just-sent message falls back to `currentUser`, whose
        // record need not be in `senderUsers`.
        const user =
          (senderId ? senderUsers.get(senderId) : undefined) ??
          (senderId && senderId === currentUser?.id ? currentUser : null);
        return userAvatar(user);
      }
      if (
        message.role === "activity" &&
        (message.activityType === A2UIActivityType ||
          message.activityType === APPROVAL_ACTIVITY_TYPE)
      ) {
        if (!senderId) return null;
        return userAvatar(senderUsers.get(senderId) ?? null);
      }
      return null;
    },
    [agentLabel, senderUsers, currentUser, resolveSenderId]
  );

  const isOwnMessage = useCallback(
    (message: Message): boolean =>
      currentUser != null && resolveSenderId(message) === currentUser.id,
    [currentUser, resolveSenderId]
  );

  return useMemo(() => ({ renderAvatar, isOwnMessage }), [renderAvatar, isOwnMessage]);
}
