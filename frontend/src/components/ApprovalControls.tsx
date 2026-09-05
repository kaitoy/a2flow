"use client";

import { useEffect, useState } from "react";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  type ApprovalDetail,
  type ApprovalStatus,
  type ApprovedCall,
  getApproval,
  getUserNames,
  isApprovalAlreadyResolvedError,
  resolveApproval,
} from "@/lib/api";
import { getApprovalCached } from "@/lib/approvalCache";
import logger from "@/lib/logger";
import { effectiveRoles, Role } from "@/lib/roles";
import { useAppSelector } from "@/store/hooks";
import { ApprovedCallList } from "./ApprovedCallList";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

/** A resolved (non-pending) approval decision. */
type Decision = Extract<ApprovalStatus, "approved" | "rejected" | "returned">;

/** How each decision is labelled and coloured once recorded. */
const DECISION_DISPLAY: Record<Decision, { label: string; className: string }> = {
  approved: { label: "Approved", className: "text-accent" },
  rejected: { label: "Rejected", className: "text-error" },
  returned: { label: "Returned for rework", className: "text-alert" },
};

/**
 * In-chat approve/reject/return controls for a pending approval request.
 *
 * "Return" is a third decision alongside approve and reject: it sends the work
 * back to be revised and re-submitted rather than settling the request, so the
 * comment matters more there than anywhere else.
 *
 * Rendered from a `render_approval` frontend tool call. Only the approval's
 * designated approver sees the decision controls; everyone else (including a
 * super admin who isn't the addressee) gets a read-only "waiting" view,
 * mirroring the backend rule that only the approver may resolve the request —
 * with no exception. An approval addressed to a user *group* treats every
 * member holding the `approver` role as its approver, and the first decision
 * from any of them settles it, so several viewers may see the controls at once
 * and one of them can lose the race (handled below as a 409).
 *
 * The calls the approval authorizes are listed above the controls, so the
 * decision is made on the actual MCP calls and their argument bounds rather
 * than on a description of them — the backend then refuses any call that
 * deviates from what is shown here.
 *
 * On click it writes the decision directly to the backend
 * (`PATCH /approvals/{id}`) and then notifies the chat via {@link onResolved} so
 * the agent run can resume with the outcome. On mount it fetches the approval to
 * reflect a decision already made (for example after reloading the session), to
 * learn who the request is addressed to, and — once decided — who decided it.
 *
 * This is a usability layer only: `ApprovalService.resolve` re-checks every
 * rule server-side and is the enforcement point.
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
  const user = useAppSelector((s) => s.auth.user);
  const currentUserId = user?.id ?? null;
  const [status, setStatus] = useState<ApprovalStatus>("pending");
  const [approver, setApprover] = useState<string | null>(null);
  const [approverGroupId, setApproverGroupId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [resolvedComment, setResolvedComment] = useState<string | null>(null);
  const [decidedBy, setDecidedBy] = useState<string | null>(null);
  // What the approval authorizes, shown while pending and kept afterwards as
  // the record of what was decided on. Empty for an approval predating
  // argument constraints.
  const [approvedCalls, setApprovedCalls] = useState<ApprovedCall[]>([]);
  const [deciderName, setDeciderName] = useState<string | null>(null);
  const action = useAsyncAction({ showDone: false });
  // Which decision is in flight, so only the clicked button shows the pending
  // label while both stay disabled.
  const [pendingDecision, setPendingDecision] = useState<Decision | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getApprovalCached(approvalId)
      .then((approval: ApprovalDetail) => {
        if (!active) return;
        setApprovedCalls(approval.approvedCalls ?? []);
        setApprover(approval.approver ?? null);
        setApproverGroupId(approval.approverGroupId ?? null);
        if (approval.status) setStatus(approval.status);
        if (approval.status && approval.status !== "pending") {
          setResolvedComment(approval.response ?? null);
          setDecidedBy(approval.decidedBy ?? null);
        }
      })
      .catch(() => {
        // Non-fatal: keep the pending controls if the lookup fails.
      });
    return () => {
      active = false;
    };
  }, [approvalId]);

  useEffect(() => {
    // Only worth a lookup for a group-addressed request: for a user-addressed
    // one the decider is necessarily the approver already shown.
    if (decidedBy == null || approverGroupId == null) {
      setDeciderName(null);
      return;
    }
    let active = true;
    getUserNames([decidedBy])
      .then((names) => {
        if (active) setDeciderName(names.get(decidedBy) ?? null);
      })
      .catch(() => {
        // Non-fatal: fall back to omitting the name.
      });
    return () => {
      active = false;
    };
  }, [decidedBy, approverGroupId]);

  /**
   * Whether the current viewer may decide this approval.
   *
   * Mirrors `ApprovalService.resolve`: the named user for a user-addressed
   * request, or — for a group-addressed one — a member of that group who holds
   * the `approver` role. `effectiveRoles` rather than `hasRole` is deliberate:
   * `hasRole` lets a super admin pass every role check, but the backend grants
   * no super-admin bypass here.
   */
  const isApprover =
    currentUserId != null &&
    (approver != null
      ? currentUserId === approver
      : approverGroupId != null &&
        (user?.groupIds ?? []).includes(approverGroupId) &&
        effectiveRoles(user).includes(Role.APPROVER));

  /** Decision controls, shown only to the approver while still pending. */
  const pendingControls = isApprover ? (
    <>
      <Textarea
        className="mt-3"
        rows={2}
        placeholder="Comment (optional)"
        value={comment}
        disabled={action.inFlight}
        onChange={(e) => setComment(e.target.value)}
        aria-label="Comment"
      />
      <div className="mt-3 flex gap-2">
        <Button
          variant="primary"
          disabled={action.inFlight}
          status={pendingDecision === "approved" ? action.status : "idle"}
          pendingLabel="Approving…"
          onClick={() => resolve("approved")}
        >
          Approve
        </Button>
        <Button
          variant="secondary"
          disabled={action.inFlight}
          status={pendingDecision === "rejected" ? action.status : "idle"}
          pendingLabel="Rejecting…"
          onClick={() => resolve("rejected")}
        >
          Reject
        </Button>
        <Button
          variant="secondary"
          disabled={action.inFlight}
          status={pendingDecision === "returned" ? action.status : "idle"}
          pendingLabel="Returning…"
          onClick={() => resolve("returned")}
        >
          Return
        </Button>
      </div>
    </>
  ) : (
    <p className="mt-3 text-sm text-on-surface-variant">
      {approverGroupId != null
        ? "Waiting for a decision from the approver group."
        : "Waiting for the approver's decision."}
    </p>
  );

  const resolve = async (decision: Decision) => {
    if (action.inFlight || status !== "pending") return;
    setError(null);
    setPendingDecision(decision);
    try {
      const trimmed = comment.trim();
      await action.run(async () => {
        await resolveApproval(approvalId, decision, trimmed || undefined);
      });
      setStatus(decision);
      setResolvedComment(trimmed || null);
      onResolved?.(toolCallId, decision);
    } catch (err) {
      if (isApprovalAlreadyResolvedError(err)) {
        // Another member of the approver group got there first. Re-read the
        // approval so the bubble shows their decision instead of stale
        // controls, and do not resume the run -- their decision already did.
        setError("Another approver already decided this request.");
        try {
          const latest = await getApproval(approvalId);
          if (latest.status) setStatus(latest.status);
          setResolvedComment(latest.response ?? null);
          setDecidedBy(latest.decidedBy ?? null);
        } catch {
          // Non-fatal: the message above already explains what happened.
        }
        return;
      }
      logger.error(err, "failed to resolve approval");
      setError("Failed to record your decision. Please try again.");
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4">
      <h3 className="text-sm font-semibold tracking-tight text-on-surface">
        {title ?? "Approval requested"}
      </h3>
      {description && <p className="mt-1 text-sm text-on-surface-variant">{description}</p>}

      <ApprovedCallList calls={approvedCalls} />

      {status === "pending" ? (
        pendingControls
      ) : (
        <>
          <p
            className={[
              "mt-3 text-sm font-medium",
              DECISION_DISPLAY[status as Decision]?.className ?? "text-on-surface-variant",
            ].join(" ")}
          >
            {DECISION_DISPLAY[status as Decision]?.label ?? status}
          </p>
          {deciderName && <p className="mt-1 text-sm text-on-surface-variant">by {deciderName}</p>}
          {resolvedComment && (
            <p className="mt-1 text-sm text-on-surface-variant">{resolvedComment}</p>
          )}
        </>
      )}

      {error && <p className="mt-2 text-sm text-error">{error}</p>}
    </div>
  );
}
