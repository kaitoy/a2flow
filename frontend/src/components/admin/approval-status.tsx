/** @module approval-status — the shared status readout for an Approval request. */
import { StatusDot } from "@/components/ui/status-dot";
import type { ApprovalStatus as ApprovalStatusValue } from "@/lib/api";

/**
 * Tailwind background-color class for the status dot of each lifecycle state,
 * keyed by the wire value.
 *
 * Deliberately reuses the palette of `lib/workflow-task-status.ts` and its
 * siblings so a dot means the same thing wherever it appears in the admin UI:
 * grey for "nothing has happened yet", green for a successful terminal state,
 * red for a failed one. `returned` takes the accent hue — the request is alive
 * again and waiting on its requester — rather than a second, near-identical red.
 */
const STATUS_DOT_CLASS: Record<ApprovalStatusValue, string> = {
  pending: "bg-on-surface-variant",
  approved: "bg-success/80",
  rejected: "bg-error",
  returned: "bg-accent",
};

/**
 * Render an approval's status as a colour-coded dot beside its name.
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
  return <StatusDot dotClass={STATUS_DOT_CLASS[value]} label={value} />;
}
