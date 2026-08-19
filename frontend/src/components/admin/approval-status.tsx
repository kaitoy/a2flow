/** @module approval-status — the shared status label for an Approval request. */
import type { ApprovalStatus as ApprovalStatusValue } from "@/lib/api";

/** Colour for each lifecycle state, keyed by the wire value. */
const STATUS_STYLES: Record<ApprovalStatusValue, string> = {
  pending: "text-on-surface-variant",
  approved: "text-accent",
  rejected: "text-error",
  returned: "text-alert",
};

/**
 * Render an approval's status as a colour-coded label.
 *
 * Shared by the approvals list and detail pages, which previously each carried
 * their own copy of the colour map — so a new lifecycle state had to be added
 * in two places to render consistently.
 *
 * @param status - The approval's status; `undefined` reads as `pending`, the
 *   state an approval starts in.
 */
export function ApprovalStatusLabel({ status }: { status?: ApprovalStatusValue | null }) {
  const value = status ?? "pending";
  return <span className={`font-medium capitalize ${STATUS_STYLES[value]}`}>{value}</span>;
}
