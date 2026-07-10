/**
 * Shared presentation helpers for {@link WorkflowTaskStatus}, used by both the
 * task list table and the DAG visualization so the two views stay in visual
 * sync.
 */

import type { WorkflowTaskStatus } from "@/lib/api";

/** All workflow-task statuses, in lifecycle order. */
export const WORKFLOW_TASK_STATUSES: WorkflowTaskStatus[] = [
  "pending",
  "in_progress",
  "completed",
  "failed",
  "skipped",
];

/** Tailwind background-color class for the small status dot of each status. */
export const STATUS_DOT_CLASS: Record<WorkflowTaskStatus, string> = {
  pending: "bg-on-surface-variant",
  in_progress: "bg-accent",
  completed: "bg-success/80",
  failed: "bg-error",
  skipped: "bg-on-surface-variant/50",
};

/**
 * Tailwind border-color class for the vertical rail that wraps a task's chat
 * messages (`border-l-*`). Uses the same palette as {@link STATUS_DOT_CLASS} so
 * the rail and dot read as one status colour.
 */
export const STATUS_RAIL_CLASS: Record<WorkflowTaskStatus, string> = {
  pending: "border-on-surface-variant",
  in_progress: "border-accent",
  completed: "border-success/80",
  failed: "border-error",
  skipped: "border-on-surface-variant/50",
};

/**
 * Human-readable label for a status (e.g. `in_progress` -> `in progress`).
 *
 * @param status - The status to format.
 * @returns The status with underscores replaced by spaces.
 */
export function formatStatusLabel(status: WorkflowTaskStatus): string {
  return status.replace("_", " ");
}
