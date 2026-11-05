/** @module AuditToolCertificateDetailPage — Read-only detail of one MCP tool certificate. */
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
  useApprovalNames,
  useUserNames,
  useWorkflowExecutionNames,
  useWorkflowTaskNames,
} from "@/hooks/useNames";
import { useT } from "@/i18n/provider";
import {
  getMcpToolCertificateById,
  isForbiddenError,
  listMcpServers,
  type McpToolCertificate,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { CERTIFICATE_GRANT_DOT_CLASS, certificateGrantLabel } from "@/lib/certificate-grant";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/**
 * Read-only detail of one MCP tool certificate.
 *
 * The granted tools are parsed back out of the signed certificate, so what this
 * page shows is what the task was actually authorized to call — not a separately
 * stored copy that could drift from it. Key material never reaches the client at
 * all.
 */
export default function AuditToolCertificateDetailPage() {
  const t = useT();
  const { certificateId } = useParams<{ certificateId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [certificate, setCertificate] = useState<McpToolCertificate | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  // Resolved separately from AuditMeta's created/updated pair: the grantor is a
  // claim of the certificate, not one of the record's audit fields.
  const grantorNames = useUserNames(certificate ? [certificate.grantedBy] : []);
  const grantorName = certificate ? grantorNames.get(certificate.grantedBy) : undefined;
  const executionNames = useWorkflowExecutionNames(
    certificate ? [certificate.workflowExecutionId] : []
  );
  const taskNames = useWorkflowTaskNames(certificate ? [certificate.workflowTaskId] : []);
  const approvalNames = useApprovalNames(certificate ? [certificate.approvalId] : []);

  useEffect(() => {
    let active = true;
    getMcpToolCertificateById(certificateId, SUPPRESS_FORBIDDEN_TOAST)
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
    { label: t("common.home"), href: "/" },
    { label: t("common.auditLogs"), href: "/audit" },
    { label: t("common.certificates"), href: "/audit/tool-certificates" },
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
        header={<AdminPageHeader title={t("audit.toolCertificate")} icon={BadgeCheck} />}
        aside={
          <AuditMeta
            createdBy={certificate.createdBy}
            updatedBy={certificate.updatedBy}
            createdAt={certificate.createdAt}
            updatedAt={certificate.updatedAt}
          />
        }
      >
        <StatusCard ariaLabel={t("audit.certificateState")}>
          {certificate.revokedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label={t("audit.revoked")} />
          ) : (
            <StatusDot dotClass="bg-success/80" label={t("audit.live")} />
          )}
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label={t("common.serialNumber")}
              value={<span className="font-mono text-xs">{certificate.serialNumber}</span>}
            />
            <DetailItem
              label={t("audit.allowedTools")}
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
              label={t("audit.authority")}
              value={
                <StatusDot
                  dotClass={CERTIFICATE_GRANT_DOT_CLASS[certificate.grantKind]}
                  label={certificateGrantLabel(certificate.grantKind)}
                />
              }
            />
            <DetailItem label={t("audit.grantedBy")} value={grantorName ?? certificate.grantedBy} />
            <DetailItem
              label={t("common.approval")}
              value={
                certificate.approvalId ? (
                  <Link
                    href={`/approvals/${certificate.approvalId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {approvalNames.get(certificate.approvalId) ?? certificate.approvalId}
                  </Link>
                ) : (
                  // No approval record exists for a grant the run's initiator
                  // gave itself.
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem
              label={t("common.workflowExecution")}
              value={
                <Link
                  href={`/workflow-executions/${certificate.workflowExecutionId}`}
                  className="text-accent transition-colors hover:underline"
                >
                  {executionNames.get(certificate.workflowExecutionId) ??
                    certificate.workflowExecutionId}
                </Link>
              }
            />
            <DetailItem
              label={t("audit.workflowTask")}
              value={
                <Link
                  href={`/workflow-executions/${certificate.workflowExecutionId}/workflow-tasks/${certificate.workflowTaskId}`}
                  className="text-accent transition-colors hover:underline"
                >
                  {taskNames.get(certificate.workflowTaskId) ?? certificate.workflowTaskId}
                </Link>
              }
            />
            <DetailItem
              label={t("audit.notBefore")}
              value={<DateTime value={certificate.notBefore} />}
            />
            <DetailItem
              label={t("audit.notAfter")}
              value={<DateTime value={certificate.notAfter} />}
            />
            <DetailItem
              label={t("audit.revokedAt")}
              value={
                certificate.revokedAt ? <DateTime value={certificate.revokedAt} /> : EMPTY_VALUE
              }
            />
            <DetailItem
              label={t("audit.revocationReason")}
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
