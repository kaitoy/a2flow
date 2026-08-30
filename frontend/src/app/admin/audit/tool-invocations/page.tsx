/** @module AuditToolInvocationsPage — Tenant-wide audit list of MCP tool-call decisions. */
"use client";

import { ShieldCheck } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { listMcpServers, listMcpToolInvocations, type McpToolInvocation } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Page size for the audit list. */
const LIMIT = 50;

/** Upper bound used to fetch the MCP server registry for server-name labels. */
const SERVER_LIMIT = 1000;

/** Filter options for the proxy's verdict. */
const DECISION_OPTIONS = [
  { label: "Allowed", value: "allowed" },
  { label: "Denied", value: "denied" },
];

/**
 * Tenant-wide list of the MCP tool calls the proxy decided on.
 *
 * These are the calls that involved a real MCP server — `allowed` ones that went
 * upstream and `denied` ones a policy vetoed on their way. A call to a mocked
 * tool never appears here whichever way it went: the proxy checks it like any
 * other, but it was always going to be answered from the run's snapshot, so it
 * reached no server. Arguments are recorded only as a digest, which is what
 * keeps a row non-repudiable without storing what the call carried.
 *
 * The per-run view of the same records lives under a workflow execution; this
 * one spans every run in the tenant and is admin-only for that reason.
 */
export default function AuditToolInvocationsPage() {
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
  } = useTableQuery<McpToolInvocation>(listMcpToolInvocations, { limit: LIMIT });

  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; the column falls back to truncated ids.
      });
  }, []);

  const names = useUserNames(rows.flatMap((r) => [r.createdBy, r.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((r) => r.tenantId) : []);

  const columns = useMemo<ColumnDef<McpToolInvocation>[]>(
    () => [
      idColumn<McpToolInvocation>(),
      {
        header: "Tool",
        sortField: "toolName",
        filterField: "toolName",
        visibility: "always",
        cell: (r) => (
          <Link
            href={`/admin/audit/tool-invocations/${r.id}`}
            className="font-mono font-medium text-accent transition-colors hover:underline"
          >
            {r.toolName}
          </Link>
        ),
      },
      {
        header: "Server",
        cell: (r) =>
          r.mcpServerId
            ? (serverNameById.get(r.mcpServerId) ?? `${r.mcpServerId.slice(0, 8)}…`)
            : EMPTY_VALUE,
      },
      {
        header: "Decision",
        noTruncate: true,
        sortField: "decision",
        filterField: "decision",
        filterOp: "eq",
        filterOptions: DECISION_OPTIONS,
        cell: (r) => <Badge>{r.decision}</Badge>,
      },
      {
        header: "Denial Reason",
        cell: (r) => r.denialReason || EMPTY_VALUE,
      },
      {
        header: "Workflow Execution",
        cell: (r) =>
          r.workflowExecutionId ? (
            <Link
              href={`/admin/workflow-executions/${r.workflowExecutionId}`}
              className="font-medium text-accent transition-colors hover:underline"
            >
              {`${r.workflowExecutionId.slice(0, 8)}…`}
            </Link>
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "Created At",
        sortField: "createdAt",
        cell: (r) => <DateTime value={r.createdAt} className="text-on-surface-variant" />,
      },
      {
        // The raw arguments are deliberately never stored: this is a SHA-256 of
        // their canonical JSON, which is what the presented signature covers.
        header: "Arguments Digest",
        visibility: "optional",
        cell: (r) => <span className="font-mono text-xs">{r.argumentsDigest.slice(0, 16)}…</span>,
      },
      {
        header: "Task",
        visibility: "optional",
        cell: (r) => (r.workflowTaskId ? `${r.workflowTaskId.slice(0, 8)}…` : EMPTY_VALUE),
      },
      {
        header: "Approval",
        visibility: "optional",
        cell: (r) =>
          r.approvalId ? (
            <Link
              href={`/admin/approvals/${r.approvalId}`}
              className="font-medium text-accent transition-colors hover:underline"
            >
              {`${r.approvalId.slice(0, 8)}…`}
            </Link>
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "Certificate",
        visibility: "optional",
        filterField: "certificateSerial",
        cell: (r) => r.certificateSerial || EMPTY_VALUE,
      },
      {
        header: "Signed At",
        visibility: "optional",
        noTruncate: true,
        cell: (r) => (r.signedAt ? <DateTime value={r.signedAt} /> : EMPTY_VALUE),
      },
      {
        header: "Session",
        visibility: "optional",
        cell: (r) => <span className="font-mono text-xs">{r.sessionId}</span>,
      },
      ...(isAllTenantsView ? [tenantColumn<McpToolInvocation>(tenantNames)] : []),
      ...auditColumns<McpToolInvocation>(names),
    ],
    [serverNameById, names, tenantNames, isAllTenantsView]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "auditToolInvocations",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Tool Invocations" },
        ]}
      />
      <AuditTabs active="tool-invocations" />
      <AdminPageHeader
        title="Tool Invocations"
        icon={ShieldCheck}
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
        emptyMessage="No MCP tool calls have been recorded yet."
        emptyIcon={ShieldCheck}
        getRowKey={(r) => r.id}
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
