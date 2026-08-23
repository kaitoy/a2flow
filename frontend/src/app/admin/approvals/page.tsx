/** @module ApprovalsPage — Admin list page for browsing approval requests. */
"use client";

import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ApprovalStatusLabel } from "@/components/admin/approval-status";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useGroupNames } from "@/hooks/useGroupNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useUserNames } from "@/hooks/useUserNames";
import { type Approval, listApprovals } from "@/lib/api";

const LIMIT = 20;

/** Admin list of approval requests ordered by most recent first. */
export default function ApprovalsPage() {
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
  } = useTableQuery<Approval>(listApprovals, { limit: LIMIT });

  // Resolve approver, decider, and audit user IDs to display names
  // (best-effort, falling back to the raw ID), mirroring AuditMeta. An approval
  // addressed to a group needs the other resolver: group ids are not users and
  // resolve-names would silently return nothing for them.
  const names = useUserNames(
    rows.flatMap((a) => [a.approver, a.decidedBy, a.createdBy, a.updatedBy])
  );
  const groupNames = useGroupNames(rows.map((a) => a.approverGroupId));

  const columns = useMemo<ColumnDef<Approval>[]>(
    () => [
      idColumn<Approval>(),
      {
        header: "Title",
        sortField: "title",
        filterField: "title",
        visibility: "always",
        cell: (a) => (
          <Link
            href={`/admin/approvals/${a.id}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {a.title}
          </Link>
        ),
      },
      {
        header: "Status",
        sortField: "status",
        filterField: "status",
        noTruncate: true,
        cell: (a) => <ApprovalStatusLabel status={a.status} />,
      },
      {
        header: "Approver",
        cell: (a) => {
          if (a.approver) return names.get(a.approver) ?? a.approver;
          if (a.approverGroupId) {
            return (
              <Link
                href={`/admin/user-groups/${a.approverGroupId}`}
                className="text-accent transition-colors hover:underline"
              >
                {groupNames.get(a.approverGroupId) ?? a.approverGroupId}
              </Link>
            );
          }
          return "—";
        },
      },
      {
        header: "Decided By",
        cell: (a) => (a.decidedBy ? (names.get(a.decidedBy) ?? a.decidedBy) : "—"),
      },
      {
        header: "Comment",
        cell: (a) => a.response ?? "—",
      },
      {
        header: "Session",
        noTruncate: true,
        cell: (a) =>
          a.workflowExecutionId ? (
            <Link
              href={`/workflow-executions/${a.workflowExecutionId}/session`}
              className="text-accent transition-colors hover:underline"
            >
              Open chat
            </Link>
          ) : (
            "—"
          ),
      },
      {
        header: "Created At",
        sortField: "createdAt",
        cell: (a) => <DateTime value={a.createdAt} className="text-on-surface-variant" />,
      },
      {
        header: "Description",
        cell: (a) => a.description || "—",
      },
      {
        header: "Decided At",
        cell: (a) =>
          a.decidedAt ? <DateTime value={a.decidedAt} className="text-on-surface-variant" /> : "—",
      },
      ...auditColumns<Approval>(names),
    ],
    [names, groupNames]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "approvals",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Approvals" }]} />
      <AdminPageHeader
        title="Approvals"
        icon={CheckCircle2}
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
        emptyMessage="No approval requests yet."
        emptyIcon={CheckCircle2}
        getRowKey={(a) => a.id}
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
