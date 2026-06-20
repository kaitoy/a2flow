"use client";

import { A2UI_OPERATIONS_KEY, A2UIActivityType, type A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { ActivityMessage } from "@ag-ui/core";
import {
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
 */
export function ActivityMessageBubble({
  message,
  onAction,
  onApprovalResolved,
}: {
  message: ActivityMessage;
  onAction?: (action: A2UIUserAction) => void;
  onApprovalResolved?: (toolCallId: string, decision: Decision) => void;
}) {
  if (message.activityType === TOOL_CALL_ACTIVITY_TYPE) {
    return <ToolActivityBubble content={message.content as unknown as ToolCallActivityContent} />;
  }
  if (message.activityType === REASONING_ACTIVITY_TYPE) {
    return <ReasoningBubble content={message.content as unknown as ReasoningActivityContent} />;
  }
  if (message.activityType === A2UIActivityType) {
    return (
      <div className="mb-3 flex justify-start">
        <div className="max-w-[85%] w-full">
          <A2uiRenderer payload={message.content[A2UI_OPERATIONS_KEY]} onAction={onAction} />
        </div>
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
      <div className="mb-3 flex justify-start">
        <div className="max-w-[85%] w-full">
          <ApprovalControls
            approvalId={content.approvalId}
            title={content.title}
            description={content.description}
            toolCallId={message.id}
            onResolved={onApprovalResolved}
          />
        </div>
      </div>
    );
  }
  return null;
}
