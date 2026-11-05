/** @module AuditToolInvocationDetailPage — Read-only detail of one MCP tool-call decision. */
"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { StatusCard } from "@/components/admin/status-card";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Badge } from "@/components/ui/badge";
import { DateTime } from "@/components/ui/date-time";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import {
  useApprovalNames,
  useWorkflowExecutionNames,
  useWorkflowTaskNames,
} from "@/hooks/useNames";
import { useT } from "@/i18n/provider";
import { translateStatus } from "@/i18n/translate";
import {
  getMcpToolInvocation,
  isForbiddenError,
  listMcpServers,
  type McpToolInvocation,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Upper bound used to fetch the MCP server registry for the server-name label. */
const SERVER_LIMIT = 1000;

/**
 * Read-only detail of one recorded MCP tool call.
 *
 * Shows the full argument digest and signature material a list row truncates.
 * The arguments themselves are deliberately never stored — the digest is what
 * the presented signature covers, which is what lets someone holding the root
 * CA's public half re-check the record later without trusting this page.
 */
export default function AuditToolInvocationDetailPage() {
  const t = useT();
  const { invocationId } = useParams<{ invocationId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [invocation, setInvocation] = useState<McpToolInvocation | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  const executionNames = useWorkflowExecutionNames(
    invocation ? [invocation.workflowExecutionId] : []
  );
  const taskNames = useWorkflowTaskNames(invocation ? [invocation.workflowTaskId] : []);
  const approvalNames = useApprovalNames(invocation ? [invocation.approvalId] : []);

  useEffect(() => {
    let active = true;
    getMcpToolInvocation(invocationId, SUPPRESS_FORBIDDEN_TOAST)
      .then((r) => {
        if (active) setInvocation(r);
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (isForbiddenError(err)) setForbidden(true);
        // Any other failure is toasted globally by api.ts.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [invocationId]);

  useEffect(() => {
    if (!invocation) return;
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // The server name is cosmetic; the field falls back to the raw id.
      });
  }, [invocation]);

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.auditLogs"), href: "/audit" },
    { label: t("common.toolInvocations"), href: "/audit/tool-invocations" },
    { label: invocation?.toolName || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !invocation) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={ShieldCheck} />}>
          <FormSkeleton fields={8} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={invocation.toolName} icon={ShieldCheck} />}
        aside={
          <AuditMeta
            createdBy={invocation.createdBy}
            updatedBy={invocation.updatedBy}
            createdAt={invocation.createdAt}
            updatedAt={invocation.updatedAt}
          />
        }
      >
        <StatusCard ariaLabel={t("audit.proxyDecision")}>
          <Badge>{translateStatus(invocation.decision, t)}</Badge>
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label={t("common.server")}
              value={serverNameById.get(invocation.mcpServerId) ?? invocation.mcpServerId}
            />
            <DetailItem
              label={t("common.denialReason")}
              value={invocation.denialReason || EMPTY_VALUE}
            />
            <DetailItem
              label={t("common.workflowExecution")}
              value={
                invocation.workflowExecutionId ? (
                  <Link
                    href={`/workflow-executions/${invocation.workflowExecutionId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {executionNames.get(invocation.workflowExecutionId) ??
                      invocation.workflowExecutionId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("audit.workflowTask")}
              value={
                invocation.workflowTaskId ? (
                  invocation.workflowExecutionId ? (
                    <Link
                      href={`/workflow-executions/${invocation.workflowExecutionId}/workflow-tasks/${invocation.workflowTaskId}`}
                      className="text-accent transition-colors hover:underline"
                    >
                      {taskNames.get(invocation.workflowTaskId) ?? invocation.workflowTaskId}
                    </Link>
                  ) : (
                    (taskNames.get(invocation.workflowTaskId) ?? invocation.workflowTaskId)
                  )
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("common.approval")}
              value={
                invocation.approvalId ? (
                  <Link
                    href={`/approvals/${invocation.approvalId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {approvalNames.get(invocation.approvalId) ?? invocation.approvalId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("audit.certificateSerial")}
              value={
                invocation.certificateSerial ? (
                  <span className="font-mono text-xs">{invocation.certificateSerial}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("common.argumentsDigest")}
              value={<span className="font-mono text-xs">{invocation.argumentsDigest}</span>}
            />
            <DetailItem
              label={t("audit.signature")}
              value={
                invocation.signature ? (
                  <span className="font-mono text-xs">{invocation.signature}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("audit.nonce")}
              value={
                invocation.nonce ? (
                  <span className="font-mono text-xs">{invocation.nonce}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("common.signedAt")}
              value={invocation.signedAt ? <DateTime value={invocation.signedAt} /> : EMPTY_VALUE}
            />
            <DetailItem
              label={t("common.session")}
              value={<span className="font-mono text-xs">{invocation.sessionId}</span>}
            />
          </DetailList>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
