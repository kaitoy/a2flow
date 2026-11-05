/** @module ApprovalsPage — Admin list page for browsing approval requests. */
"use client";

import { CheckCircle2, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ApprovalStatusLabel } from "@/components/admin/approval-status";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tagsColumn } from "@/components/admin/tag-columns";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  useGroupNames,
  useTenantNames,
  useUserNames,
  useWorkflowExecutionNames,
} from "@/hooks/useNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useT } from "@/i18n/provider";
import { type ApprovalDetail, listApprovals } from "@/lib/api";

const LIMIT = 20;

/** Admin list of approval requests ordered by most recent first. */
export default function ApprovalsPage() {
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
  } = useTableQuery<ApprovalDetail>(listApprovals, { limit: LIMIT });

  // Resolve approver, decider, and audit user IDs to display names
  // (best-effort, falling back to the raw ID), mirroring AuditMeta. An approval
  // addressed to a group needs the other resolver: group ids are not users and
  // resolve-names would silently return nothing for them.
  const names = useUserNames(
    rows.flatMap((a) => [a.approver, a.decidedBy, a.createdBy, a.updatedBy])
  );
  const groupNames = useGroupNames(rows.map((a) => a.approverGroupId));
  const executionNames = useWorkflowExecutionNames(rows.map((a) => a.workflowExecutionId));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((a) => a.tenantId) : []);
  const { byId: tagsById } = useTags();

  const columns = useMemo<ColumnDef<ApprovalDetail>[]>(
    () => [
      ...(isAllTenantsView ? [tenantColumn<ApprovalDetail>(tenantNames)] : []),
      idColumn<ApprovalDetail>(),
      {
        header: "common.title",
        sortField: "title",
        filterField: "title",
        visibility: "always",
        cell: (a) => (
          <Link
            href={`/approvals/${a.id}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {a.title}
          </Link>
        ),
      },
      {
        header: "common.workflowExecution",
        cell: (a) => (
          <Link
            href={`/workflow-executions/${a.workflowExecutionId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {executionNames.get(a.workflowExecutionId) ?? a.workflowExecutionId}
          </Link>
        ),
      },
      {
        header: "common.status",
        sortField: "status",
        filterField: "status",
        noTruncate: true,
        cell: (a) => <ApprovalStatusLabel status={a.status} />,
      },
      {
        header: "common.description",
        cell: (a) => a.description || "—",
      },
      {
        header: "common.createdAt",
        sortField: "createdAt",
        cell: (a) => <DateTime value={a.createdAt} className="text-on-surface-variant" />,
      },
      {
        header: "approvals.approver",
        visibility: "optional",
        cell: (a) => {
          if (a.approver) return names.get(a.approver) ?? a.approver;
          if (a.approverGroupId) {
            return (
              <Link
                href={`/user-groups/${a.approverGroupId}`}
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
        header: "approvals.decidedBy",
        visibility: "optional",
        cell: (a) => (a.decidedBy ? (names.get(a.decidedBy) ?? a.decidedBy) : "—"),
      },
      {
        header: "common.comment",
        visibility: "optional",
        cell: (a) => a.response ?? "—",
      },
      {
        header: "approvals.decidedAt",
        visibility: "optional",
        cell: (a) =>
          a.decidedAt ? <DateTime value={a.decidedAt} className="text-on-surface-variant" /> : "—",
      },
      ...auditColumns<ApprovalDetail>(names),
      tagsColumn<ApprovalDetail>((a) => a.tagIds, tagsById),
      {
        header: "common.actions",
        noTruncate: true,
        visibility: "always",
        cell: (a) => (
          <div className="flex justify-center gap-2">
            <ActionIconButton
              icon={MessageSquareText}
              label={t("common.openWorkflowSession")}
              href={`/workflow-executions/${a.workflowExecutionId}/session`}
            />
          </div>
        ),
      },
    ],
    [names, groupNames, executionNames, tenantNames, isAllTenantsView, tagsById, t]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "approvals",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[{ label: t("common.home"), href: "/" }, { label: t("common.approvals") }]}
      />
      <AdminPageHeader
        title={t("common.approvals")}
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
        emptyMessage={t("approvals.noApprovalRequestsYet")}
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
