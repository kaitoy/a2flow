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
 * The statuses a viewer can actually encounter, for the status filter options.
 *
 * Someone who cannot edit workflows never sees `draft` (the backend hides those
 * rows) and never sees `modified` (the backend reports such a workflow as
 * `published`, showing its last published version). Offering either would be a
 * filter that always comes back empty.
 *
 * @param canEdit - True when the viewer holds `developer` (or `super_admin`).
 * @returns The statuses worth offering, in lifecycle order.
 */
export function visibleWorkflowStatuses(canEdit: boolean): WorkflowStatus[] {
  if (canEdit) return WORKFLOW_STATUSES;
  return WORKFLOW_STATUSES.filter((s) => s !== "draft" && s !== "modified");
}

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

/** Permissions gating whether the current viewer may execute a given workflow. */
export interface WorkflowExecutePermissions {
  /** True when the viewer may execute workflows (`requester` or `developer`). */
  canRun: boolean;
  /** True when the viewer may create, edit, and delete workflows (`developer`). */
  canEdit: boolean;
}

/**
 * True when a workflow in `status` is runnable by a viewer holding `permissions`.
 *
 * Mirrors the backend's rule (`WorkflowService.execute`): `published` and
 * `modified` workflows are runnable by anyone with the Run action at all — a
 * `modified` run uses the last published version — while `draft` workflows are
 * runnable only by someone who can also edit workflows (`developer`, or
 * `super_admin` via `canEdit`'s bypass) — pre-publish testing.
 */
export function canExecuteWorkflow(
  status: WorkflowStatus | undefined,
  permissions: WorkflowExecutePermissions
): boolean {
  return (
    status === "published" || status === "modified" || (status === "draft" && permissions.canEdit)
  );
}
