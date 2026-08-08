"use client";

import { A2UIActivityType } from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { type ReactNode, useCallback } from "react";
import { AgentAvatar } from "@/components/AgentAvatar";
import { Avatar } from "@/components/ui/avatar";
import { Tooltip } from "@/components/ui/tooltip";
import { A2UI_SOURCE_TOOL_CALL_ID_KEY } from "@/lib/agentActivity";
import { formatUserName, type User } from "@/lib/api";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";

/** Inputs for {@link useSessionAvatarRenderer}. */
export interface SessionAvatarRendererOptions {
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

/**
 * Build the `renderAvatar` callback `MessageList` uses to show who sent a message.
 *
 * Shared by both session chats — a workflow session and a design session are
 * each one ADK conversation several people post into, so both need the same
 * sender-to-avatar resolution:
 *
 * - `assistant` messages get the agent's glyph, tooltipped with `agentLabel`.
 * - `user` messages resolve through the attribution map, then through the ids
 *   this viewer just sent (their optimistic client ids differ from the persisted
 *   ADK event ids, so they are absent from the map until a reload), then fall
 *   back to the session's owner.
 * - A2UI surfaces resolve by the tool call id that produced them, and approval
 *   controls by their own id (which *is* the `render_approval` tool call id), so
 *   the avatar names whoever acted on them. Both show nothing until someone has.
 *
 * @param options - See {@link SessionAvatarRendererOptions}.
 * @returns A stable callback mapping a message to the avatar node beside it.
 */
export function useSessionAvatarRenderer({
  agentLabel,
  ownerUserId,
  messageSenders,
  senderUsers,
  locallySentMessageIds,
  currentUser,
}: SessionAvatarRendererOptions): (message: Message) => ReactNode {
  return useCallback(
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
      if (message.role === "user") {
        const senderId = messageSenders.get(message.id);
        let user: User | null;
        if (senderId) {
          user = senderUsers.get(senderId) ?? null;
        } else if (locallySentMessageIds.has(message.id)) {
          user = currentUser;
        } else {
          user = senderUsers.get(ownerUserId) ?? null;
        }
        return userAvatar(user);
      }
      if (message.role === "activity" && message.activityType === A2UIActivityType) {
        const toolCallId = message.content[A2UI_SOURCE_TOOL_CALL_ID_KEY];
        const senderId =
          typeof toolCallId === "string" ? messageSenders.get(toolCallId) : undefined;
        if (!senderId) return null;
        return userAvatar(senderUsers.get(senderId) ?? null);
      }
      if (message.role === "activity" && message.activityType === APPROVAL_ACTIVITY_TYPE) {
        // An approval activity's id is the render_approval tool call id, which is
        // also the key the decision's tool result is attributed under — so the
        // sender lookup resolves to the user who approved or rejected.
        const senderId = messageSenders.get(message.id);
        if (!senderId) return null;
        return userAvatar(senderUsers.get(senderId) ?? null);
      }
      return null;
    },
    [agentLabel, ownerUserId, messageSenders, senderUsers, locallySentMessageIds, currentUser]
  );
}
