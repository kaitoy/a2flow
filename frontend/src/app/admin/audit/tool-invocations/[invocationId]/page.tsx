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
  const { invocationId } = useParams<{ invocationId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [invocation, setInvocation] = useState<McpToolInvocation | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

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
    { label: "Admin", href: "/admin" },
    { label: "Audit Logs", href: "/admin/audit" },
    { label: "Tool Invocations", href: "/admin/audit/tool-invocations" },
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
        <StatusCard ariaLabel="Proxy decision">
          <Badge>{invocation.decision}</Badge>
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label="Server"
              value={serverNameById.get(invocation.mcpServerId) ?? invocation.mcpServerId}
            />
            <DetailItem label="Denial Reason" value={invocation.denialReason || EMPTY_VALUE} />
            <DetailItem
              label="Workflow Execution"
              value={
                invocation.workflowExecutionId ? (
                  <Link
                    href={`/admin/workflow-executions/${invocation.workflowExecutionId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {invocation.workflowExecutionId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem label="Workflow Task" value={invocation.workflowTaskId || EMPTY_VALUE} />
            <DetailItem
              label="Approval"
              value={
                invocation.approvalId ? (
                  <Link
                    href={`/admin/approvals/${invocation.approvalId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {invocation.approvalId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label="Certificate Serial"
              value={
                invocation.certificateSerial ? (
                  <span className="font-mono text-xs">{invocation.certificateSerial}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label="Arguments Digest"
              value={<span className="font-mono text-xs">{invocation.argumentsDigest}</span>}
            />
            <DetailItem
              label="Signature"
              value={
                invocation.signature ? (
                  <span className="font-mono text-xs">{invocation.signature}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label="Nonce"
              value={
                invocation.nonce ? (
                  <span className="font-mono text-xs">{invocation.nonce}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label="Signed At"
              value={invocation.signedAt ? <DateTime value={invocation.signedAt} /> : EMPTY_VALUE}
            />
            <DetailItem
              label="Session"
              value={<span className="font-mono text-xs">{invocation.sessionId}</span>}
            />
          </DetailList>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
