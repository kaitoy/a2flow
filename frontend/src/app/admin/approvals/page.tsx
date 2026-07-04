/** @module ApprovalsPage — Admin list page for browsing approval requests. */
"use client";

import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { ErrorBanner } from "@/components/ui/error-banner";
import { useTableQuery } from "@/hooks/useTableQuery";
import { type Approval, type ApprovalStatus, getUserNames, listApprovals } from "@/lib/api";

const LIMIT = 20;

const STATUS_STYLES: Record<ApprovalStatus, string> = {
  pending: "text-on-surface-variant",
  approved: "text-accent",
  rejected: "text-error",
};

/** Admin list of approval requests ordered by most recent first. */
export default function ApprovalsPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<Approval>(listApprovals, {
      limit: LIMIT,
      errorMessage: "Failed to load approvals",
    });

  // Resolve the intended approvers' user IDs to display names (best-effort,
  // falling back to the raw ID), mirroring AuditMeta. The comma-joined key lets
  // the effect depend on the set of IDs without re-running on array identity.
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const approverKey = rows
    .map((a) => a.approver)
    .filter(Boolean)
    .join(",");
  useEffect(() => {
    if (!approverKey) return;
    let active = true;
    getUserNames(approverKey.split(","))
      .then((resolved) => {
        if (active) setNames(resolved);
      })
      .catch(() => {
        // Name resolution is best-effort; the raw ID is shown as a fallback.
      });
    return () => {
      active = false;
    };
  }, [approverKey]);

  const columns = useMemo<ColumnDef<Approval>[]>(
    () => [
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
        header: "Approver",
        cell: (a) => (a.approver ? (names.get(a.approver) ?? a.approver) : "—"),
      },
      {
        header: "Comment",
        cell: (a) => a.response ?? "—",
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
    ],
    [names]
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Approvals" }]} />
      <AdminPageHeader
        title="Approvals"
        icon={CheckCircle2}
        onRefresh={reload}
        refreshing={loading}
      />
      <div className="mb-4">
        <ErrorBanner error={error} />
      </div>
      <DataTable
        columns={columns}
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
