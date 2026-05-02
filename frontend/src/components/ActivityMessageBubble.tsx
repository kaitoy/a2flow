"use client";

import { A2UI_OPERATIONS_KEY, A2UIActivityType, type A2UIUserAction } from "@ag-ui/a2ui-middleware";
import type { ActivityMessage } from "@ag-ui/core";
import { A2uiRenderer } from "./A2uiRenderer";

export function ActivityMessageBubble({
  message,
  onAction,
}: {
  message: ActivityMessage;
  onAction?: (action: A2UIUserAction) => void;
}) {
  if (message.activityType !== A2UIActivityType) return null;
  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[85%]">
        <A2uiRenderer payload={message.content[A2UI_OPERATIONS_KEY]} onAction={onAction} />
      </div>
    </div>
  );
}
