/** @module AuditToolCertificatesPage — Audit list of the certificates authorizing MCP tool calls. */
"use client";

import { BadgeCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { AuditTabs } from "@/components/admin/audit-tabs";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { Chip } from "@/components/ui/chip";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { StatusDot } from "@/components/ui/status-dot";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  useApprovalNames,
  useTenantNames,
  useUserNames,
  useWorkflowExecutionNames,
  useWorkflowTaskNames,
} from "@/hooks/useNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useT } from "@/i18n/provider";
import { listMcpServers, listMcpToolCertificates, type McpToolCertificate } from "@/lib/api";
import { CERTIFICATE_GRANT_DOT_CLASS, certificateGrantLabel } from "@/lib/certificate-grant";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Page size for the audit list. */
const LIMIT = 50;

/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/**
 * Audit list of the certificates authorizing tasks' MCP tool calls.
 *
 * A certificate is what actually lets a task call its bound tools, and every
 * proxied call presents one — so this is the complete record of what each run
 * was authorized to do: which tools, on whose authority, until when, and whether
 * the grant has since been revoked. The tools are parsed back out of the signed
 * certificate rather than read from a column, so the list can never report a
 * grant that differs from what was signed. Key material is never part of the
 * response.
 */
export default function AuditToolCertificatesPage() {
  const t = useT();
  const {
    rows,
    loading,
    refreshing,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload,
  } = useTableQuery<McpToolCertificate>(listMcpToolCertificates, { limit: LIMIT });

  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, []);

  const names = useUserNames(rows.flatMap((c) => [c.grantedBy, c.createdBy, c.updatedBy]));
  const executionNames = useWorkflowExecutionNames(rows.map((c) => c.workflowExecutionId));
  const taskNames = useWorkflowTaskNames(rows.map((c) => c.workflowTaskId));
  const approvalNames = useApprovalNames(rows.map((c) => c.approvalId));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((c) => c.tenantId) : []);

  const columns = useMemo<ColumnDef<McpToolCertificate>[]>(
    () => [
      ...(isAllTenantsView ? [tenantColumn<McpToolCertificate>(tenantNames)] : []),
      idColumn<McpToolCertificate>(),
      {
        header: "audit.serial",
        filterField: "serialNumber",
        visibility: "always",
        cell: (c) => (
          <Link
            href={`/audit/tool-certificates/${c.id}`}
            className="font-mono font-medium text-accent transition-colors hover:underline"
          >
            {c.serialNumber}
          </Link>
        ),
      },
      {
        header: "audit.authority",
        filterField: "grantKind",
        sortField: "grantKind",
        noTruncate: true,
        cell: (c) => (
          <StatusDot
            dotClass={CERTIFICATE_GRANT_DOT_CLASS[c.grantKind]}
            label={certificateGrantLabel(c.grantKind)}
          />
        ),
      },
      {
        header: "audit.grantedBy",
        cell: (c) => names.get(c.grantedBy) ?? c.grantedBy,
      },
      {
        // Null for a grant the run's initiator gave itself: there is no
        // approval record to link to, which is the point of that grant kind.
        header: "common.approval",
        visibility: "optional",
        cell: (c) =>
          c.approvalId ? (
            <Link
              href={`/approvals/${c.approvalId}`}
              className="font-medium text-accent transition-colors hover:underline"
            >
              {approvalNames.get(c.approvalId) ?? c.approvalId}
            </Link>
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        // Revocation is derived from `revokedAt` rather than shown as a stored
        // status: verification also re-reads the approval and the task, so a
        // grant can stop counting before anything stamps the column.
        header: "audit.state",
        noTruncate: true,
        cell: (c) =>
          c.revokedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label={t("audit.revoked")} />
          ) : (
            <StatusDot dotClass="bg-success/80" label={t("audit.live")} />
          ),
      },
      {
        header: "audit.allowedTools",
        cell: (c) =>
          c.allowedTools.length === 0 ? (
            EMPTY_VALUE
          ) : (
            <div className="flex flex-wrap gap-1">
              {c.allowedTools.map((t) => (
                <Chip
                  key={`${t.mcpServerId}:${t.toolName}`}
                  label={`${serverNameById.get(t.mcpServerId) ?? `${t.mcpServerId.slice(0, 8)}…`}: ${t.toolName}`}
                />
              ))}
            </div>
          ),
      },
      {
        header: "audit.notAfter",
        sortField: "notAfter",
        cell: (c) => <DateTime value={c.notAfter} className="text-on-surface-variant" />,
      },
      {
        header: "audit.revokedAt",
        sortField: "revokedAt",
        cell: (c) =>
          c.revokedAt ? (
            <DateTime value={c.revokedAt} className="text-on-surface-variant" />
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "audit.revocationReason",
        visibility: "optional",
        cell: (c) =>
          c.revocationReason ? (
            <span className="capitalize">{c.revocationReason.replace("_", " ")}</span>
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "audit.notBefore",
        visibility: "optional",
        sortField: "notBefore",
        cell: (c) => <DateTime value={c.notBefore} className="text-on-surface-variant" />,
      },
      {
        header: "common.workflowExecution",
        visibility: "optional",
        cell: (c) => (
          <Link
            href={`/workflow-executions/${c.workflowExecutionId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {executionNames.get(c.workflowExecutionId) ?? c.workflowExecutionId}
          </Link>
        ),
      },
      {
        header: "audit.workflowTask",
        visibility: "optional",
        cell: (c) => (
          <Link
            href={`/workflow-executions/${c.workflowExecutionId}/workflow-tasks/${c.workflowTaskId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {taskNames.get(c.workflowTaskId) ?? c.workflowTaskId}
          </Link>
        ),
      },
      ...auditColumns<McpToolCertificate>(names),
    ],
    [
      serverNameById,
      names,
      executionNames,
      taskNames,
      approvalNames,
      tenantNames,
      isAllTenantsView,
      t,
    ]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "auditToolCertificates",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: t("common.home"), href: "/" },
          { label: t("common.auditLogs"), href: "/audit" },
          { label: t("common.certificates") },
        ]}
      />
      <AuditTabs active="tool-certificates" />
      <AdminPageHeader
        title={t("audit.toolCertificates")}
        icon={BadgeCheck}
        onRefresh={reload}
        refreshing={loading || refreshing}
        columnPicker={
          <ColumnPicker
            options={options}
            value={selected}
            onChange={setSelected}
            onReset={reset}
            customized={customized}
          />
        }
      />
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage={t("audit.noTaskHasBeenGrantedToolAuthority")}
        emptyIcon={BadgeCheck}
        getRowKey={(c) => c.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={rows.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
    </AdminPageContainer>
  );
}
