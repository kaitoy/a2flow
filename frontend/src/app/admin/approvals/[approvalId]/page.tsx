/** @module ApprovalDetailPage — Read-only admin detail page for a single Approval request. */
"use client";

import { CheckCircle2, MessageSquareText, ShieldCheck } from "lucide-react";
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
import { StatusCard } from "@/components/admin/status-card";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  type Approval,
  getApproval,
  getUserGroup,
  getUserNames,
  getWorkflowExecution,
  getWorkflowTask,
  isForbiddenError,
  listApprovalCertificates,
  listMcpServers,
  listWorkflowTasks,
  type McpToolCertificateRead,
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
  const [executionName, setExecutionName] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [certificates, setCertificates] = useState<McpToolCertificateRead[]>([]);
  const [serverNames, setServerNames] = useState<Map<string, string>>(new Map());
  const [coveredTaskTitles, setCoveredTaskTitles] = useState<Map<string, string>>(new Map());
  const isAllTenantsView = useIsAllTenantsView();

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
          tenantId: isAllTenantsView ? a.tenantId : undefined,
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
        // The workflow execution always exists; the task only when this approval
        // named one. Both use SUPPRESS_FORBIDDEN_TOAST like every other lookup here,
        // so a permission failure on either folds into the same access-denied state
        // instead of a second toast.
        const execution = await getWorkflowExecution(
          a.workflowExecutionId,
          SUPPRESS_FORBIDDEN_TOAST
        );
        if (!active) return;
        setExecutionName(execution.name);
        if (a.workflowTaskId) {
          const task = await getWorkflowTask(a.workflowTaskId, SUPPRESS_FORBIDDEN_TOAST);
          if (!active) return;
          setTaskTitle(task.title);
        }
        // Only fetched once the approval is granted: nothing is issued before
        // that. The list can still legitimately come back empty, since a
        // covered task is granted its certificate only when it starts.
        if (a.status === "approved") {
          const issued = await listApprovalCertificates(approvalId);
          if (!active) return;
          setCertificates(issued);
          if (issued.length > 0) {
            // Both lookups are per-page rather than per-certificate: the run's
            // tasks name the rows, the servers name the tools inside them.
            const [servers, tasks] = await Promise.all([
              listMcpServers({ limit: 1000 }),
              listWorkflowTasks(a.workflowExecutionId, { limit: 1000 }),
            ]);
            if (!active) return;
            setServerNames(new Map(servers.map((s) => [s.id, s.name])));
            setCoveredTaskTitles(new Map(tasks.map((t) => [t.id, t.title])));
          }
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
  }, [approvalId, isAllTenantsView]);

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
        <StatusCard ariaLabel="Approval status">
          <ApprovalStatusLabel status={status} />
        </StatusCard>

        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
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
                  {executionName ?? approval.workflowExecutionId}
                </Link>
              }
            />
            <DetailItem
              label="Takes Effect From"
              value={
                approval.workflowTaskId ? (
                  <Link
                    href={`/admin/workflow-executions/${approval.workflowExecutionId}/workflow-tasks/${approval.workflowTaskId}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {taskTitle ?? approval.workflowTaskId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
          </DetailList>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/approvals")}>
              Back
            </Button>
          </div>
        </div>

        {approval.status === "approved" && (
          <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
            <div className="flex items-center gap-2">
              <ShieldCheck size={18} strokeWidth={1.8} aria-hidden="true" className="text-accent" />
              <h2 className="font-semibold text-base">Authorized MCP tools</h2>
            </div>
            <p className="text-muted-foreground text-sm">
              This approval covers the task it names and every task after it, up to the next
              approval. Each of those tasks is issued its own certificate when it starts, over
              exactly the tools it binds at that moment — changing them afterwards is refused.
            </p>
            {certificates.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No certificate has been issued under this approval yet.
              </p>
            ) : (
              certificates.map((certificate) => (
                <DetailList key={certificate.id} singleColumn>
                  <DetailItem
                    label="Task"
                    value={
                      <Link
                        href={`/admin/workflow-executions/${approval.workflowExecutionId}/workflow-tasks/${certificate.workflowTaskId}`}
                        className="font-medium text-accent transition-colors hover:underline"
                      >
                        {coveredTaskTitles.get(certificate.workflowTaskId) ??
                          certificate.workflowTaskId}
                      </Link>
                    }
                  />
                  <DetailItem
                    label="Certificate Status"
                    value={
                      certificate.revokedAt
                        ? `Revoked${certificate.revocationReason ? ` (${certificate.revocationReason})` : ""}`
                        : "Active"
                    }
                  />
                  <DetailItem
                    label="Serial Number"
                    value={
                      <span className="break-all font-mono text-xs">
                        {certificate.serialNumber}
                      </span>
                    }
                  />
                  <DetailItem
                    label="Valid Until"
                    value={new Date(certificate.notAfter).toLocaleString()}
                  />
                  <DetailItem
                    label="Granted Tools"
                    value={
                      certificate.allowedTools.length === 0 ? (
                        EMPTY_VALUE
                      ) : (
                        <ul className="flex flex-col gap-1">
                          {certificate.allowedTools.map((tool) => (
                            <li key={`${tool.mcpServerId}/${tool.toolName}`} className="text-sm">
                              <span className="font-mono text-xs">{tool.toolName}</span>
                              <span className="text-muted-foreground">
                                {" · "}
                                {serverNames.get(tool.mcpServerId) ?? tool.mcpServerId}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )
                    }
                  />
                </DetailList>
              ))
            )}
          </div>
        )}
      </FormLayout>
    </AdminPageContainer>
  );
}
