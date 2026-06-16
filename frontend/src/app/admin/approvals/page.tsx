/** @module ApprovalsPage — Admin list page for browsing approval requests. */
"use client";

import Link from "next/link";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useTableQuery } from "@/hooks/useTableQuery";
import { type Approval, type ApprovalStatus, listApprovals } from "@/lib/api";

const LIMIT = 20;

const STATUS_STYLES: Record<ApprovalStatus, string> = {
  pending: "text-on-surface-variant",
  approved: "text-accent",
  rejected: "text-error",
};

const COLUMNS: ColumnDef<Approval>[] = [
  {
    header: "Title",
    sortField: "title",
    filterField: "title",
    cell: (a) => <span className="font-medium">{a.title}</span>,
  },
  {
    header: "Status",
    sortField: "status",
    filterField: "status",
    cell: (a) => (
      <span className={`font-medium capitalize ${STATUS_STYLES[a.status ?? "pending"]}`}>
        {a.status ?? "pending"}
      </span>
    ),
  },
  {
    header: "Session",
    noTruncate: true,
    cell: (a) =>
      a.workflowSessionId ? (
        <Link
          href={`/workflow-sessions/${a.workflowSessionId}`}
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
];

/** Admin list of approval requests ordered by most recent first. */
export default function ApprovalsPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters } =
    useTableQuery<Approval>(listApprovals, {
      limit: LIMIT,
      errorMessage: "Failed to load approvals",
    });

  return (
    <div className="mx-auto max-w-6xl p-8">
      <AdminPageHeader title="Approvals" />
      <ErrorBanner error={error} />
      <DataTable
        columns={COLUMNS}
        rows={rows}
        loading={loading}
        emptyMessage="No approval requests yet."
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
    </div>
  );
}
