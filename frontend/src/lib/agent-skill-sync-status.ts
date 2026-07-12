/**
 * Shared presentation helpers for {@link SkillSyncStatus}, used by the agent
 * skill list table and the skill edit form so the two views stay in visual sync.
 *
 * Mirrors `lib/workflow-task-status.ts`, and deliberately reuses its palette so
 * a status dot means the same thing wherever it appears in the admin UI.
 */

import type { SkillSyncStatus } from "@/lib/api";

/** Tailwind background-color class for the small status dot of each status. */
export const SYNC_STATUS_DOT_CLASS: Record<SkillSyncStatus, string> = {
  pending: "bg-accent",
  ready: "bg-success/80",
  failed: "bg-error",
};

/**
 * Human-readable label for a sync status.
 *
 * `pending` reads as "Cloning" rather than "Pending": the job is the only thing
 * that clears the state, so from the admin's point of view the clone is what is
 * happening, not a queue they are waiting in.
 *
 * @param status - The status to format.
 * @returns The label to render next to the status dot.
 */
export function formatSyncStatusLabel(status: SkillSyncStatus): string {
  return status === "pending" ? "Cloning" : status;
}

/**
 * Shorten a commit sha for display, Git-style.
 *
 * @param commitSha - The full 40-character sha, or nullish when the skill has
 *   no published revision yet.
 * @returns The first 7 characters, or an em dash when there is no revision.
 */
export function formatRevision(commitSha: string | null | undefined): string {
  return commitSha ? commitSha.slice(0, 7) : "—";
}
