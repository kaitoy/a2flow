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
  completed: "bg-green-500/80",
  failed: "bg-error",
  skipped: "bg-on-surface-variant/50",
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
