"use client";

import { A2UI_OPERATIONS_KEY, A2UIActivityType, type A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { ActivityMessage } from "@ag-ui/core";
import { type ReactNode, useMemo } from "react";
import {
  mergeRecoveredValuesIntoPayload,
  parseActionContent,
  RENDER_ACK_CONTENT,
} from "@/lib/a2uiAction";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  REASONING_ACTIVITY_TYPE,
  type ReasoningActivityContent,
  TOOL_CALL_ACTIVITY_TYPE,
  type ToolCallActivityContent,
} from "@/lib/agentActivity";
import { APPROVAL_ACTIVITY_TYPE } from "@/lib/approvalTool";
import { A2uiRenderer } from "./A2uiRenderer";
import { ApprovalControls } from "./ApprovalControls";
import { ReasoningBubble } from "./ReasoningBubble";
import { ToolActivityBubble } from "./ToolActivityBubble";

/** A resolved (non-pending) approval decision. */
type Decision = "approved" | "rejected";

/**
 * Render an activity message by delegating to the renderer for its type: A2UI
 * surfaces to {@link A2uiRenderer}, approval requests to {@link ApprovalControls},
 * tool-call status lines to {@link ToolActivityBubble}, and streamed reasoning to
 * {@link ReasoningBubble}. Ignores unknown activity types.
 *
 * `avatar` is used by the A2UI branch (the user who resolved the surface's
 * pending action) and the approval branch (the user who decided the approval);
 * other branches ignore it. `isThinking` is used only by the reasoning branch,
 * to drive its live edge while the agent is still actively reasoning.
 *
 * `pendingToolCallIds` and `toolResultContentByCallId` (both derived from the full
 * session history by `MessageList`) drive the A2UI branch: a surface whose
 * `render_a2ui` call id is absent from `pendingToolCallIds` is already resolved and
 * renders inert (see {@link A2uiRenderer}'s `resolved` prop), pre-filled with the
 * data model the resolving tool message recorded — so a reloaded session shows the
 * values the user submitted rather than the agent's defaults.
 */
export function ActivityMessageBubble({
  message,
  avatar,
  isThinking,
  onAction,
  onApprovalResolved,
  pendingToolCallIds,
  toolResultContentByCallId,
}: {
  message: ActivityMessage;
  avatar?: ReactNode;
  isThinking?: boolean;
  onAction?: (action: A2UIUserAction, values: Record<string, unknown>) => void;
  onApprovalResolved?: (toolCallId: string, decision: Decision) => void;
  pendingToolCallIds?: Set<string>;
  toolResultContentByCallId?: Map<string, string>;
}) {
  // A2UI branch data, computed unconditionally (hooks can't follow the early
  // returns below) but only meaningful when activityType === A2UIActivityType.
  const payload = message.content[A2UI_OPERATIONS_KEY];
  const sourceToolCallId = message.content[A2UI_SOURCE_TOOL_CALL_ID_KEY];
  const isResolved =
    typeof sourceToolCallId === "string" && !pendingToolCallIds?.has(sourceToolCallId);
  const resolvedContent =
    isResolved && typeof sourceToolCallId === "string"
      ? toolResultContentByCallId?.get(sourceToolCallId)
      : undefined;
  // Depends on the raw content string (stable across renders), not the object
  // parseActionContent returns (a fresh reference every call), so displayPayload
  // keeps its identity and A2uiRenderer doesn't rebuild the surface every render.
  const displayPayload = useMemo(() => {
    // RENDER_ACK_CONTENT means the call was auto-acknowledged, not actually
    // answered by the user — nothing to recover.
    if (!resolvedContent || resolvedContent === RENDER_ACK_CONTENT) return payload;
    const values = parseActionContent(resolvedContent)?.values;
    return values ? mergeRecoveredValuesIntoPayload(payload, values) : payload;
  }, [payload, resolvedContent]);

  if (message.activityType === TOOL_CALL_ACTIVITY_TYPE) {
    return <ToolActivityBubble content={message.content as unknown as ToolCallActivityContent} />;
  }
  if (message.activityType === REASONING_ACTIVITY_TYPE) {
    return (
      <ReasoningBubble
        content={message.content as unknown as ReasoningActivityContent}
        isThinking={isThinking}
      />
    );
  }
  if (message.activityType === A2UIActivityType) {
    // The middleware also emits lifecycle snapshots (e.g. { status: "building" })
    // under the same activity type; only snapshots carrying operations are renderable.
    if (payload == null) return null;
    return (
      <div
        className={avatar ? "mb-3 flex justify-start items-end gap-2" : "mb-3 flex justify-start"}
      >
        <div className="max-w-[85%] w-full">
          <A2uiRenderer
            payload={displayPayload}
            onAction={isResolved ? undefined : onAction}
            resolved={isResolved}
          />
        </div>
        {avatar}
      </div>
    );
  }
  if (message.activityType === APPROVAL_ACTIVITY_TYPE) {
    const content = message.content as {
      approvalId?: string;
      title?: string;
      description?: string;
    };
    if (!content.approvalId) return null;
    return (
      <div
        className={avatar ? "mb-3 flex justify-start items-end gap-2" : "mb-3 flex justify-start"}
      >
        <div className="max-w-[85%] w-full">
          <ApprovalControls
            approvalId={content.approvalId}
            title={content.title}
            description={content.description}
            toolCallId={message.id}
            onResolved={onApprovalResolved}
          />
        </div>
        {avatar}
      </div>
    );
  }
  return null;
}
