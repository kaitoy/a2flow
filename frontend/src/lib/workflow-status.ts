/**
 * Shared presentation helpers for {@link WorkflowStatus}, used by the workflow
 * list table and the workflow detail form so the two views stay in visual sync.
 *
 * Mirrors `lib/agent-skill-sync-status.ts`, and deliberately reuses its palette
 * so a status dot means the same thing wherever it appears in the admin UI.
 */

import type { WorkflowStatus } from "@/lib/api";

/** Every workflow lifecycle status, in lifecycle order (for filter options). */
export const WORKFLOW_STATUSES: WorkflowStatus[] = ["generating", "draft", "failed", "published"];

/** Tailwind background-color class for the small status dot of each status. */
export const WORKFLOW_STATUS_DOT_CLASS: Record<WorkflowStatus, string> = {
  generating: "bg-accent",
  draft: "bg-on-surface-variant",
  failed: "bg-error",
  published: "bg-success/80",
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
