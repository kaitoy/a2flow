/** @module AuditApprovalCertificateDetailPage — Read-only detail of one approval certificate. */
"use client";

import { BadgeCheck } from "lucide-react";
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
import { Chip } from "@/components/ui/chip";
import { DateTime } from "@/components/ui/date-time";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { StatusDot } from "@/components/ui/status-dot";
import {
  type ApprovalCertificate,
  getApprovalCertificateById,
  isForbiddenError,
  listMcpServers,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/**
 * Read-only detail of one approval certificate.
 *
 * The granted tools are parsed back out of the signed certificate, so what this
 * page shows is what the approval actually authorized — not a separately stored
 * copy that could drift from it. Key material never reaches the client at all.
 */
export default function AuditApprovalCertificateDetailPage() {
  const { certificateId } = useParams<{ certificateId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [certificate, setCertificate] = useState<ApprovalCertificate | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let active = true;
    getApprovalCertificateById(certificateId, SUPPRESS_FORBIDDEN_TOAST)
      .then((c) => {
        if (active) setCertificate(c);
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
  }, [certificateId]);

  useEffect(() => {
    if (!certificate || certificate.allowedTools.length === 0) return;
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, [certificate]);

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Audit Logs", href: "/admin/audit" },
    { label: "Certificates", href: "/admin/audit/approval-certificates" },
    { label: certificate?.serialNumber || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !certificate) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={BadgeCheck} />}>
          <FormSkeleton fields={7} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title="Approval Certificate" icon={BadgeCheck} />}
        aside={
          <AuditMeta
            createdBy={certificate.createdBy}
            updatedBy={certificate.updatedBy}
            createdAt={certificate.createdAt}
            updatedAt={certificate.updatedAt}
          />
        }
      >
        <StatusCard ariaLabel="Certificate state">
          {certificate.revokedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label="Revoked" />
          ) : (
            <StatusDot dotClass="bg-success/80" label="Live" />
          )}
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label="Serial Number"
              value={<span className="font-mono text-xs">{certificate.serialNumber}</span>}
            />
            <DetailItem
              label="Allowed Tools"
              value={
                certificate.allowedTools.length === 0 ? (
                  EMPTY_VALUE
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {certificate.allowedTools.map((t) => (
                      <Chip
                        key={`${t.mcpServerId}:${t.toolName}`}
                        label={`${serverNameById.get(t.mcpServerId) ?? `${t.mcpServerId.slice(0, 8)}…`}: ${t.toolName}`}
                      />
                    ))}
                  </div>
                )
              }
            />
            <DetailItem
              label="Approval"
              value={
                <Link
                  href={`/admin/approvals/${certificate.approvalId}`}
                  className="text-accent transition-colors hover:underline"
                >
                  {certificate.approvalId}
                </Link>
              }
            />
            <DetailItem
              label="Workflow Execution"
              value={
                <Link
                  href={`/admin/workflow-executions/${certificate.workflowExecutionId}`}
                  className="text-accent transition-colors hover:underline"
                >
                  {certificate.workflowExecutionId}
                </Link>
              }
            />
            <DetailItem label="Workflow Task" value={certificate.workflowTaskId} />
            <DetailItem label="Not Before" value={<DateTime value={certificate.notBefore} />} />
            <DetailItem label="Not After" value={<DateTime value={certificate.notAfter} />} />
            <DetailItem
              label="Revoked At"
              value={
                certificate.revokedAt ? <DateTime value={certificate.revokedAt} /> : EMPTY_VALUE
              }
            />
            <DetailItem
              label="Revocation Reason"
              value={
                certificate.revocationReason ? (
                  <span className="capitalize">
                    {certificate.revocationReason.replace("_", " ")}
                  </span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
          </DetailList>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
