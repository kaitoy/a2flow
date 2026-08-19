/** @module ApprovalDetailPage — Read-only admin detail page for a single Approval request. */
"use client";

import { CheckCircle2, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ApprovalStatusLabel } from "@/components/admin/approval-status";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import {
  type Approval,
  getApproval,
  getUserGroup,
  getUserNames,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

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
  const [forbidden, setForbidden] = useState(false);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [approverName, setApproverName] = useState<string | null>(null);
  const [approverGroupName, setApproverGroupName] = useState<string | null>(null);
  const [deciderName, setDeciderName] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  useEffect(() => {
    let active = true;
    getApproval(approvalId, SUPPRESS_FORBIDDEN_TOAST)
      .then(async (a) => {
        if (!active) return;
        setApproval(a);
        setAudit({
          createdBy: a.createdBy,
          updatedBy: a.updatedBy,
          createdAt: a.createdAt,
          updatedAt: a.updatedAt,
        });
        // One batched lookup for both user references the page can show.
        const userIds = [a.approver, a.decidedBy].filter((id): id is string => !!id);
        if (userIds.length > 0) {
          const names = await getUserNames(userIds);
          if (!active) return;
          if (a.approver) setApproverName(names.get(a.approver) ?? null);
          if (a.decidedBy) setDeciderName(names.get(a.decidedBy) ?? null);
        }
        if (a.approverGroupId) {
          const group = await getUserGroup(a.approverGroupId, SUPPRESS_FORBIDDEN_TOAST);
          if (active) setApproverGroupName(group.name);
        }
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
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

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

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
                onClick={() =>
                  router.push(`/workflow-executions/${approval.workflowExecutionId}/session`)
                }
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
            <DetailItem label="Status" value={<ApprovalStatusLabel status={status} />} />
            <DetailItem label="Description" value={approval.description || EMPTY_VALUE} />
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
                ) : approval.approverGroupId ? (
                  <Link
                    href={`/admin/user-groups/${approval.approverGroupId}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {approverGroupName ?? approval.approverGroupId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label="Decided By"
              value={
                approval.decidedBy ? (
                  <Link
                    href={`/admin/users/${approval.decidedBy}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {deciderName ?? approval.decidedBy}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem label="Comment" value={approval.response ?? EMPTY_VALUE} />
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
              value={
                <span className="font-mono text-xs">{approval.workflowTaskId ?? EMPTY_VALUE}</span>
              }
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
