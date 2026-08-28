/** @module ToolInvocationsPage — Read-only admin view of a run's MCP tool-call audit. */
"use client";

import { ShieldCheck } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { Badge } from "@/components/ui/badge";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useUserNames } from "@/hooks/useUserNames";
import {
  getWorkflowExecution,
  listMcpServers,
  listWorkflowExecutionToolInvocations,
  type McpToolInvocation,
} from "@/lib/api";

/** Page size for the audit list. */
const PAGE_LIMIT = 50;
/** Upper bound used to fetch the MCP server registry for server-name labels. */
const SERVER_LIMIT = 1000;

/** Filter options for the proxy's verdict. */
const DECISION_OPTIONS = [
  { label: "Allowed", value: "allowed" },
  { label: "Denied", value: "denied" },
];

function buildColumns(
  serverNameById: Map<string, string>,
  names: Map<string, string>
): ColumnDef<McpToolInvocation>[] {
  return [
    idColumn<McpToolInvocation>(),
    {
      header: "Tool",
      sortField: "toolName",
      filterField: "toolName",
      visibility: "always",
      cell: (r) => <span className="font-mono text-on-surface">{r.toolName}</span>,
    },
    {
      header: "Server",
      cell: (r) =>
        r.mcpServerId
          ? (serverNameById.get(r.mcpServerId) ?? `${r.mcpServerId.slice(0, 8)}…`)
          : "—",
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
      cell: (r) => r.denialReason || "—",
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
      cell: (r) => (r.workflowTaskId ? `${r.workflowTaskId.slice(0, 8)}…` : "—"),
    },
    {
      header: "Approval",
      visibility: "optional",
      cell: (r) => (r.approvalId ? `${r.approvalId.slice(0, 8)}…` : "—"),
    },
    {
      header: "Certificate",
      visibility: "optional",
      cell: (r) => r.certificateSerial || "—",
    },
    {
      header: "Signed At",
      visibility: "optional",
      noTruncate: true,
      cell: (r) => (r.signedAt ? <DateTime value={r.signedAt} /> : "—"),
    },
    ...auditColumns<McpToolInvocation>(names),
  ];
}

/**
 * Read-only admin list of the MCP tool calls a run's proxy decided on.
 *
 * These are the calls that involved a real MCP server — `allowed` ones that went
 * upstream and `denied` ones a policy vetoed on their way. A call to a mocked
 * tool never appears here whichever way it went: the proxy checks it like any
 * other, but it was always going to be answered from the run's snapshot, so it
 * reached no server. The run's chat transcript is where a stubbed call's
 * arguments and result are inspected. Arguments are recorded only as a digest,
 * which is what keeps the row non-repudiable without storing what the call
 * carried.
 */
export default function ToolInvocationsPage() {
  const { executionId } = useParams<{ executionId: string }>();
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
  } = useTableQuery<McpToolInvocation>(
    (query) => listWorkflowExecutionToolInvocations(executionId, query),
    { limit: PAGE_LIMIT }
  );
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  // The parent run's name, shown as a breadcrumb crumb linking back to it.
  const [workflowName, setWorkflowName] = useState("");

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; the column falls back to truncated ids.
      });
  }, []);

  useEffect(() => {
    getWorkflowExecution(executionId)
      .then((s) => setWorkflowName(s.name))
      .catch(() => {
        // Failure toast is shown globally by api.ts; the breadcrumb crumb
        // simply stays as an ellipsis.
      });
  }, [executionId]);

  const names = useUserNames(rows.flatMap((r) => [r.createdBy, r.updatedBy]));
  const columns = buildColumns(serverNameById, names);
  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "toolInvocations",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Executions", href: "/admin/workflow-executions" },
          { label: workflowName || "…", href: `/admin/workflow-executions/${executionId}` },
          { label: "Tool Invocations" },
        ]}
      />
      <AdminPageHeader
        title="Tool Invocations"
        icon={ShieldCheck}
        onRefresh={reload}
        refreshing={refreshing}
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
        emptyMessage="No MCP tool calls were recorded for this run."
        emptyIcon={ShieldCheck}
        getRowKey={(r) => r.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
      />
      <PaginationControls
        offset={offset}
        limit={PAGE_LIMIT}
        count={rows.length}
        onPrev={() => setOffset((o) => Math.max(0, o - PAGE_LIMIT))}
        onNext={() => setOffset((o) => o + PAGE_LIMIT)}
      />
    </AdminPageContainer>
  );
}
