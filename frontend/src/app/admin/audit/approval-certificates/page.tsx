/** @module AuditApprovalCertificatesPage — Audit list of the certificates granted approvals carry. */
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
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { type ApprovalCertificate, listApprovalCertificates, listMcpServers } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Page size for the audit list. */
const LIMIT = 50;

/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/**
 * Audit list of the certificates issued when approvals were granted.
 *
 * A certificate is what actually lets an approved task call its bound tools, so
 * this is the record of what each approval authorized: which tools, until when,
 * and whether the grant has since been revoked. The tools are parsed back out of
 * the signed certificate rather than read from a column, so the list can never
 * report a grant that differs from what was signed. Key material is never part
 * of the response.
 */
export default function AuditApprovalCertificatesPage() {
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
  } = useTableQuery<ApprovalCertificate>(listApprovalCertificates, { limit: LIMIT });

  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, []);

  const names = useUserNames(rows.flatMap((c) => [c.createdBy, c.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((c) => c.tenantId) : []);

  const columns = useMemo<ColumnDef<ApprovalCertificate>[]>(
    () => [
      idColumn<ApprovalCertificate>(),
      {
        header: "Serial",
        filterField: "serialNumber",
        visibility: "always",
        cell: (c) => (
          <Link
            href={`/admin/audit/approval-certificates/${c.id}`}
            className="font-mono font-medium text-accent transition-colors hover:underline"
          >
            {c.serialNumber}
          </Link>
        ),
      },
      {
        header: "Approval",
        cell: (c) => (
          <Link
            href={`/admin/approvals/${c.approvalId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {`${c.approvalId.slice(0, 8)}…`}
          </Link>
        ),
      },
      {
        // Revocation is derived from `revokedAt` rather than shown as a stored
        // status: verification also re-reads the approval and the task, so a
        // grant can stop counting before anything stamps the column.
        header: "State",
        noTruncate: true,
        cell: (c) =>
          c.revokedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label="Revoked" />
          ) : (
            <StatusDot dotClass="bg-success/80" label="Live" />
          ),
      },
      {
        header: "Allowed Tools",
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
        header: "Not After",
        sortField: "notAfter",
        cell: (c) => <DateTime value={c.notAfter} className="text-on-surface-variant" />,
      },
      {
        header: "Revoked At",
        sortField: "revokedAt",
        cell: (c) =>
          c.revokedAt ? (
            <DateTime value={c.revokedAt} className="text-on-surface-variant" />
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "Revocation Reason",
        visibility: "optional",
        cell: (c) =>
          c.revocationReason ? (
            <span className="capitalize">{c.revocationReason.replace("_", " ")}</span>
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "Not Before",
        visibility: "optional",
        sortField: "notBefore",
        cell: (c) => <DateTime value={c.notBefore} className="text-on-surface-variant" />,
      },
      {
        header: "Workflow Execution",
        visibility: "optional",
        cell: (c) => (
          <Link
            href={`/admin/workflow-executions/${c.workflowExecutionId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {`${c.workflowExecutionId.slice(0, 8)}…`}
          </Link>
        ),
      },
      {
        header: "Workflow Task",
        visibility: "optional",
        cell: (c) => `${c.workflowTaskId.slice(0, 8)}…`,
      },
      ...(isAllTenantsView ? [tenantColumn<ApprovalCertificate>(tenantNames)] : []),
      ...auditColumns<ApprovalCertificate>(names),
    ],
    [serverNameById, names, tenantNames, isAllTenantsView]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "auditApprovalCertificates",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Certificates" },
        ]}
      />
      <AuditTabs active="approval-certificates" />
      <AdminPageHeader
        title="Approval Certificates"
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
        emptyMessage="No approval has granted tool authority yet."
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
