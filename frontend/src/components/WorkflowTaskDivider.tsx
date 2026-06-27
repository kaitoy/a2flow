"use client";

import type { WorkflowTask } from "@/lib/api";
import { formatStatusLabel, STATUS_DOT_CLASS } from "@/lib/workflow-task-status";

/**
 * Props for {@link WorkflowTaskDivider}.
 */
export interface WorkflowTaskDividerProps {
  /**
   * The task this boundary introduces. Optional because the message-to-task
   * association can resolve before the task list has loaded; the divider falls
   * back to a generic label until the task is known.
   */
  task?: WorkflowTask;
  /**
   * DOM id used as the scroll anchor when a timeline entry is selected. Only the
   * first divider for a given task carries one, so ids stay unique.
   */
  anchorId?: string;
}

/**
 * Inline boundary inserted into the chat stream where the agent switched to a
 * new workflow task. Messages below it (until the next divider) belong to this
 * task, mirroring the highlighted entry in the {@link WorkflowTaskTimeline}.
 */
export function WorkflowTaskDivider({ task, anchorId }: WorkflowTaskDividerProps) {
  const status = task?.status ?? "pending";
  return (
    <div id={anchorId} className="my-3 flex scroll-mt-4 items-center gap-2">
      <span className="h-px flex-1 bg-glass-border" aria-hidden="true" />
      <span className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs glass-panel">
        <span
          className={`inline-block size-2 rounded-full ${STATUS_DOT_CLASS[status]}`}
          aria-hidden="true"
        />
        <span className="font-medium text-on-surface">{task?.title ?? "タスク"}</span>
        <span className="text-on-surface-variant">{formatStatusLabel(status)}</span>
      </span>
      <span className="h-px flex-1 bg-glass-border" aria-hidden="true" />
    </div>
  );
}
