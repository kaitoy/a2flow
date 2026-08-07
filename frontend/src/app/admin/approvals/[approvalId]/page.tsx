/** @module ApprovalDetailPage — Read-only admin detail page for a single Approval request. */
"use client";

import { CheckCircle2, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { Button } from "@/components/ui/button";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { type Approval, type ApprovalStatus, getApproval, getUserNames } from "@/lib/api";

/** Placeholder shown in place of an attribute that has no value. */
const EMPTY = "—";

const STATUS_STYLES: Record<ApprovalStatus, string> = {
  pending: "text-on-surface-variant",
  approved: "text-accent",
  rejected: "text-error",
};

/**
 * Read-only detail page for a single `Approval` request: its status, the
 * approver's decision and comment, and the workflow execution it belongs to.
 *
 * Approve/reject is deliberately not offered here — resolving an approval
 * stays in the in-chat flow (`ApprovalControls`), the only place the backend
 * accepts a decision from. This page exists purely so an approval can be
 * looked up and reviewed from the admin list, matching every other entity's
 * detail page.
 */
export default function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [approverName, setApproverName] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  useEffect(() => {
    let active = true;
    getApproval(approvalId)
      .then(async (a) => {
        if (!active) return;
        setApproval(a);
        setAudit({
          createdBy: a.createdBy,
          updatedBy: a.updatedBy,
          createdAt: a.createdAt,
          updatedAt: a.updatedAt,
        });
        if (!a.approver) return;
        const names = await getUserNames([a.approver]);
        if (active) setApproverName(names.get(a.approver) ?? null);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [approvalId]);

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Approvals", href: "/admin/approvals" },
    { label: approval?.title || "…" },
  ];

  if (loading || !approval) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={CheckCircle2} />}>
          <FormSkeleton fields={5} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  const status = approval.status ?? "pending";

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={approval.title}
            icon={CheckCircle2}
            secondaryAction={
              <HeaderIconButton
                label="Open workflow session"
                onClick={() => router.push(`/workflow-sessions/${approval.workflowExecutionId}`)}
              >
                <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
              </HeaderIconButton>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label="Status"
              value={
                <span className={`font-medium capitalize ${STATUS_STYLES[status]}`}>{status}</span>
              }
            />
            <DetailItem label="Description" value={approval.description || EMPTY} />
            <DetailItem
              label="Approver"
              value={
                approval.approver ? (
                  <Link
                    href={`/admin/users/${approval.approver}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {approverName ?? approval.approver}
                  </Link>
                ) : (
                  EMPTY
                )
              }
            />
            <DetailItem label="Comment" value={approval.response ?? EMPTY} />
            <DetailItem
              label="Workflow Execution"
              value={
                <Link
                  href={`/admin/workflow-executions/${approval.workflowExecutionId}`}
                  className="font-medium text-accent transition-colors hover:underline"
                >
                  Open session
                </Link>
              }
            />
            <DetailItem
              label="Related Task"
              value={<span className="font-mono text-xs">{approval.workflowTaskId ?? EMPTY}</span>}
            />
          </DetailList>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/approvals")}>
              Back
            </Button>
          </div>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
