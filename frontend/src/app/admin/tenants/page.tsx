/**
 * @module TenantsPage — Admin list page for managing tenant organizations.
 *
 * Reads are open to every authenticated user, so a viewer without the super
 * admin role sees the list but neither the Add button nor the per-row Delete —
 * the same convention the detail page follows by rendering read-only. The
 * section is already hidden from the sidebar for such a viewer; this covers the
 * deep link.
 */
"use client";

import { Building2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteTenant, listTenants, type Tenant } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { tenantsChanged } from "@/store/tenantsSlice";

const LIMIT = 20;

/** Yes/No options for the boolean `eq` column filter. */
const BOOL_FILTER_OPTIONS = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
];

const STATIC_COLUMNS: ColumnDef<Tenant>[] = [
  {
    header: "Display Name",
    sortField: "displayName",
    filterField: "displayName",
    visibility: "always",
    cell: (t) => (
      <Link
        href={`/admin/tenants/${t.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {t.displayName}
      </Link>
    ),
  },
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    cell: (t) => t.name,
  },
  {
    header: "Enabled",
    sortField: "enabled",
    filterField: "enabled",
    filterOp: "eq",
    filterOptions: BOOL_FILTER_OPTIONS,
    className: "text-center",
    cell: (t) => (t.enabled ? "✓" : "—"),
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (t) => <DateTime value={t.createdAt} className="text-on-surface-variant" />,
  },
];

export default function TenantsPage() {
  const canEdit = useHasRole(Role.SUPER_ADMIN);
  const dispatch = useAppDispatch();
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
  } = useTableQuery<Tenant>(listTenants, { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, displayName: string) {
    setConfirmTarget({ id, name: displayName });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteTenant(confirmTarget.id);
      setConfirmTarget(null);
      dispatch(tenantsChanged());
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Tenant>[] = [
    ...STATIC_COLUMNS,
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (tenant: Tenant) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton onClick={() => handleDelete(tenant.id, tenant.displayName)} />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "tenants",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tenants" }]} />
      <AdminPageHeader
        title="Tenants"
        icon={Building2}
        addHref={canEdit ? "/admin/tenants/new" : undefined}
        addLabel="+ Add tenant"
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
        emptyMessage="No tenants registered yet."
        emptyIcon={Building2}
        getRowKey={(tenant) => tenant.id}
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
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete Tenant"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
