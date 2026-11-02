/**
 * Shared presentation helpers for {@link KnowledgeSourceStatus}, so every view of
 * a knowledge source shows its state the same way.
 *
 * Reuses the palette of `lib/agent-skill-sync-status.ts`: accent while the
 * background job still has work to do, green once done, red on failure, and
 * the muted gray `lib/workflow-task-status.ts` gives a task not yet started for
 * a source nobody has asked to be read yet.
 */

import type { KnowledgeSourceStatus } from "@/lib/api";

/** Tailwind background-color class for the status dot of each state. */
export const KNOWLEDGE_SOURCE_STATUS_DOT_CLASS: Record<KnowledgeSourceStatus, string> = {
  unread: "bg-on-surface-variant",
  pending: "bg-accent",
  ingesting: "bg-accent",
  ready: "bg-success/80",
  failed: "bg-error",
  removing: "bg-accent",
};

/** Human-readable label for each state. */
const LABELS: Record<KnowledgeSourceStatus, string> = {
  unread: "Not read",
  pending: "Queued",
  ingesting: "Reading",
  ready: "Ready",
  failed: "Failed",
  removing: "Removing",
};

/**
 * Label to render next to a source's status dot.
 *
 * @param status - The source's state.
 * @returns Its label.
 */
export function formatKnowledgeSourceStatus(status: KnowledgeSourceStatus): string {
  return LABELS[status];
}

/**
 * Whether the background job still has work to do on a source, i.e. whether a
 * view showing it should keep polling.
 *
 * @param status - The source's state.
 * @returns `true` until the source is ready or has failed.
 */
export function isKnowledgeSourceBusy(status: KnowledgeSourceStatus): boolean {
  return status === "pending" || status === "ingesting" || status === "removing";
}

/**
 * Whether the LLM agent is working on a source right now — reading it into the
 * pages or taking its claims back out — as opposed to merely queued.
 *
 * @param status - The source's state.
 * @returns `true` while the source is being read or removed.
 */
export function isKnowledgeSourceLlmActive(status: KnowledgeSourceStatus): boolean {
  return status === "ingesting" || status === "removing";
}
