"use client";

import { useEffect, useState } from "react";
import { type Approval, type ApprovalStatus, getApproval, resolveApproval } from "@/lib/api";
import logger from "@/lib/logger";
import { Button } from "./ui/button";

/** A resolved (non-pending) approval decision. */
type Decision = Extract<ApprovalStatus, "approved" | "rejected">;

/**
 * In-chat approve/reject controls for a pending approval request.
 *
 * Rendered from a `render_approval` frontend tool call. On click it writes the
 * decision directly to the backend (`PATCH /approvals/{id}`) and then notifies
 * the chat via {@link onResolved} so the agent run can resume with the outcome.
 * On mount it fetches the approval to reflect a decision already made (for
 * example after reloading the session).
 */
export function ApprovalControls({
  approvalId,
  title,
  description,
  toolCallId,
  onResolved,
}: {
  approvalId: string;
  title?: string;
  description?: string;
  toolCallId: string;
  onResolved?: (toolCallId: string, decision: Decision) => void;
}) {
  const [status, setStatus] = useState<ApprovalStatus>("pending");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getApproval(approvalId)
      .then((approval: Approval) => {
        if (active && approval.status) setStatus(approval.status);
      })
      .catch(() => {
        // Non-fatal: keep the pending controls if the lookup fails.
      });
    return () => {
      active = false;
    };
  }, [approvalId]);

  const resolve = async (decision: Decision) => {
    if (busy || status !== "pending") return;
    setBusy(true);
    setError(null);
    try {
      await resolveApproval(approvalId, decision);
      setStatus(decision);
      onResolved?.(toolCallId, decision);
    } catch (err) {
      logger.error(err, "failed to resolve approval");
      setError("Failed to record your decision. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4">
      <h3 className="text-sm font-semibold tracking-tight text-on-surface">
        {title ?? "Approval requested"}
      </h3>
      {description && <p className="mt-1 text-sm text-on-surface-variant">{description}</p>}

      {status === "pending" ? (
        <div className="mt-3 flex gap-2">
          <Button variant="primary" disabled={busy} onClick={() => resolve("approved")}>
            Approve
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => resolve("rejected")}>
            Reject
          </Button>
        </div>
      ) : (
        <p
          className={[
            "mt-3 text-sm font-medium",
            status === "approved" ? "text-accent" : "text-on-surface-variant",
          ].join(" ")}
        >
          {status === "approved" ? "Approved" : "Rejected"}
        </p>
      )}

      {error && <p className="mt-2 text-sm text-error">{error}</p>}
    </div>
  );
}
