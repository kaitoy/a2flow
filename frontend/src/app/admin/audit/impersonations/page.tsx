/** @module AuditImpersonationsPage — Audit list of who acted as whom, and when. */
"use client";

import { VenetianMask } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { idColumn } from "@/components/admin/audit-columns";
import { AuditTabs } from "@/components/admin/audit-tabs";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { StatusDot } from "@/components/ui/status-dot";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { type ImpersonationEvent, listImpersonationEvents } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Page size for the audit list. */
const LIMIT = 50;

/**
 * Audit list of impersonation sessions: one row per admin acting as another
 * user, from the moment they start until they stop.
 *
 * Rows are scoped by the *impersonated* account's tenant, not the actor's. That
 * is what makes a platform-scoped super admin's session visible to the tenant
 * whose data it touched — they carry no tenant of their own, so scoping on the
 * actor would hide exactly the sessions most worth seeing.
 *
 * The Tenant column shows the impersonated account's tenant for the same reason,
 * so it is built here rather than through the shared `tenantColumn`, which reads
 * a record's own `tenantId`.
 */
export default function AuditImpersonationsPage() {
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
  } = useTableQuery<ImpersonationEvent>(listImpersonationEvents, { limit: LIMIT });

  const names = useUserNames(rows.flatMap((e) => [e.impersonatorId, e.targetUserId]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((e) => e.targetTenantId) : []);

  const columns = useMemo<ColumnDef<ImpersonationEvent>[]>(() => {
    const userLink = (id: string) => (
      <Link
        href={`/admin/users/${id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {names.get(id) ?? id}
      </Link>
    );
    return [
      idColumn<ImpersonationEvent>(),
      {
        header: "Impersonator",
        filterField: "impersonatorId",
        visibility: "always",
        cell: (e) => userLink(e.impersonatorId),
      },
      {
        header: "Target User",
        filterField: "targetUserId",
        cell: (e) => userLink(e.targetUserId),
      },
      {
        // Derived from `endedAt` rather than stored: a session is open until it
        // is closed, so there is no third state a status column could show.
        // Colours follow the task palette — accent for still-running, muted for
        // finished (see STATUS_DOT_CLASS in lib/workflow-task-status).
        header: "State",
        noTruncate: true,
        cell: (e) =>
          e.endedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label="Ended" />
          ) : (
            <StatusDot dotClass="bg-accent" label="Active" />
          ),
      },
      {
        header: "Started At",
        sortField: "startedAt",
        cell: (e) => <DateTime value={e.startedAt} className="text-on-surface-variant" />,
      },
      {
        header: "Ended At",
        sortField: "endedAt",
        cell: (e) =>
          e.endedAt ? (
            <DateTime value={e.endedAt} className="text-on-surface-variant" />
          ) : (
            EMPTY_VALUE
          ),
      },
      ...(isAllTenantsView
        ? [
            {
              header: "Target Tenant",
              cell: (e: ImpersonationEvent) => {
                const id = e.targetTenantId;
                if (!id) return EMPTY_VALUE;
                return (
                  <Link
                    href={`/admin/tenants/${id}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {tenantNames.get(id) ?? id}
                  </Link>
                );
              },
            } satisfies ColumnDef<ImpersonationEvent>,
          ]
        : []),
      {
        header: "Actions",
        noTruncate: true,
        visibility: "always",
        cell: (e) => (
          <div className="flex justify-center">
            <Link
              href={`/admin/audit/impersonations/${e.id}`}
              className="font-medium text-accent transition-colors hover:underline"
            >
              Details
            </Link>
          </div>
        ),
      },
    ];
  }, [names, tenantNames, isAllTenantsView]);

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "auditImpersonations",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Impersonations" },
        ]}
      />
      <AuditTabs active="impersonations" />
      <AdminPageHeader
        title="Impersonations"
        icon={VenetianMask}
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
        emptyMessage="No one has acted as another user yet."
        emptyIcon={VenetianMask}
        getRowKey={(e) => e.id}
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
