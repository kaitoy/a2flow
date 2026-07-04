"use client";

import type { ReactNode } from "react";
import type { WorkflowTask } from "@/lib/api";
import { formatStatusLabel, STATUS_RAIL_CLASS } from "@/lib/workflow-task-status";

/**
 * Props for {@link WorkflowTaskGroup}.
 */
export interface WorkflowTaskGroupProps {
  /**
   * The task whose consecutive messages this group wraps. Optional because the
   * message-to-task association can resolve before the task list has loaded; the
   * heading falls back to a generic label until the task is known.
   */
  task?: WorkflowTask;
  /**
   * 1-based ordinal shown in the heading badge. Shared with the matching
   * {@link WorkflowTaskTimeline} entry so the eye can pair the two views.
   */
  index: number;
  /**
   * DOM id used as the scroll anchor when a timeline entry is selected. Only the
   * first group for a given task carries one, so ids stay unique.
   */
  anchorId?: string;
  /** Whether this group is the focused task (scroll-spy or hover), shown emphasized. */
  isHighlighted: boolean;
  /** Called with the task id on mouse enter and `null` on leave, to drive timeline linkage. */
  onHover: (taskId: string | null) => void;
  /** The message bubbles belonging to this task run. */
  children: ReactNode;
}

/**
 * Wraps one workflow task's consecutive chat messages in a status-coloured left
 * rail with a numbered heading, so the boundary of each task is obvious at a
 * glance. The shared ordinal badge plus hover/highlight linkage tie the group to
 * its entry in the {@link WorkflowTaskTimeline}; it replaces the former
 * single-line task divider.
 */
export function WorkflowTaskGroup({
  task,
  index,
  anchorId,
  isHighlighted,
  onHover,
  children,
}: WorkflowTaskGroupProps) {
  const status = task?.status ?? "pending";
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: hover is a non-essential visual link to the timeline; the core linkage is click + scroll-spy
    <section
      id={anchorId}
      data-task-id={task?.id}
      onMouseEnter={() => {
        if (task) onHover(task.id);
      }}
      onMouseLeave={() => onHover(null)}
      className={`my-3 scroll-mt-4 rounded-r-lg border-l-2 py-2 pl-4 pr-2 transition-all ${
        STATUS_RAIL_CLASS[status]
      } ${isHighlighted ? "bg-glass shadow-glow" : ""}`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 bg-surface text-[11px] font-semibold leading-none text-on-surface ${STATUS_RAIL_CLASS[status]}`}
        >
          {index}
        </span>
        <span className="truncate text-sm font-medium text-on-surface">
          {task?.title ?? "Task"}
        </span>
        <span className="shrink-0 text-xs text-on-surface-variant">
          {formatStatusLabel(status)}
        </span>
      </div>
      {children}
    </section>
  );
}
