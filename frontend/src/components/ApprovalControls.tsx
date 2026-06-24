"use client";

import { useEffect, useState } from "react";
import { type Approval, type ApprovalStatus, getApproval, resolveApproval } from "@/lib/api";
import logger from "@/lib/logger";
import { useAppSelector } from "@/store/hooks";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

/** A resolved (non-pending) approval decision. */
type Decision = Extract<ApprovalStatus, "approved" | "rejected">;

/**
 * In-chat approve/reject controls for a pending approval request.
 *
 * Rendered from a `render_approval` frontend tool call. Only the approval's
 * designated approver sees the approve/reject controls; everyone else gets a
 * read-only "waiting" view, mirroring the backend rule that only the approver may
 * resolve the request. On click it writes the decision directly to the backend
 * (`PATCH /approvals/{id}`) and then notifies the chat via {@link onResolved} so
 * the agent run can resume with the outcome. On mount it fetches the approval to
 * reflect a decision already made (for example after reloading the session) and
 * to learn who the designated approver is.
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
  const currentUserId = useAppSelector((s) => s.auth.user?.id ?? null);
  const [status, setStatus] = useState<ApprovalStatus>("pending");
  const [approver, setApprover] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [resolvedComment, setResolvedComment] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getApproval(approvalId)
      .then((approval: Approval) => {
        if (!active) return;
        setApprover(approval.approver ?? null);
        if (approval.status) setStatus(approval.status);
        if (approval.status && approval.status !== "pending") {
          setResolvedComment(approval.response ?? null);
        }
      })
      .catch(() => {
        // Non-fatal: keep the pending controls if the lookup fails.
      });
    return () => {
      active = false;
    };
  }, [approvalId]);

  /** Whether the current viewer is the approval's designated approver. */
  const isApprover = currentUserId != null && currentUserId === approver;

  /** Approve/reject controls, shown only to the approver while still pending. */
  const pendingControls = isApprover ? (
    <>
      <Textarea
        className="mt-3"
        rows={2}
        placeholder="Comment (optional)"
        value={comment}
        disabled={busy}
        onChange={(e) => setComment(e.target.value)}
        aria-label="Comment"
      />
      <div className="mt-3 flex gap-2">
        <Button variant="primary" disabled={busy} onClick={() => resolve("approved")}>
          Approve
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => resolve("rejected")}>
          Reject
        </Button>
      </div>
    </>
  ) : (
    <p className="mt-3 text-sm text-on-surface-variant">Waiting for the approver's decision.</p>
  );

  const resolve = async (decision: Decision) => {
    if (busy || status !== "pending") return;
    setBusy(true);
    setError(null);
    try {
      const trimmed = comment.trim();
      await resolveApproval(approvalId, decision, trimmed || undefined);
      setStatus(decision);
      setResolvedComment(trimmed || null);
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
        pendingControls
      ) : (
        <>
          <p
            className={[
              "mt-3 text-sm font-medium",
              status === "approved" ? "text-accent" : "text-on-surface-variant",
            ].join(" ")}
          >
            {status === "approved" ? "Approved" : "Rejected"}
          </p>
          {resolvedComment && (
            <p className="mt-1 text-sm text-on-surface-variant">{resolvedComment}</p>
          )}
        </>
      )}

      {error && <p className="mt-2 text-sm text-error">{error}</p>}
    </div>
  );
}
