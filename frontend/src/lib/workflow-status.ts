/**
 * Shared presentation helpers for {@link WorkflowStatus}, used by the workflow
 * list table and the workflow detail form so the two views stay in visual sync.
 *
 * Mirrors `lib/agent-skill-sync-status.ts`, and deliberately reuses its palette
 * so a status dot means the same thing wherever it appears in the admin UI.
 */

import type { WorkflowStatus } from "@/lib/api";

/** Every workflow lifecycle status, in lifecycle order (for filter options). */
export const WORKFLOW_STATUSES: WorkflowStatus[] = [
  "generating",
  "draft",
  "failed",
  "published",
  "modified",
];

/**
 * Tailwind background-color class for the small status dot of each status.
 *
 * `modified` reuses the published hue at lower opacity: the workflow is still
 * released and runnable — its last published version is what runs — but it
 * carries edits that have not been published yet.
 */
export const WORKFLOW_STATUS_DOT_CLASS: Record<WorkflowStatus, string> = {
  generating: "bg-accent",
  draft: "bg-on-surface-variant",
  failed: "bg-error",
  published: "bg-success/80",
  modified: "bg-success/40",
};

/**
 * Human-readable label for a workflow status.
 *
 * @param status - The status to format.
 * @returns The label to render next to the status dot.
 */
export function formatWorkflowStatusLabel(status: WorkflowStatus): string {
  return status;
}
