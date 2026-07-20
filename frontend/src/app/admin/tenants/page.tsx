/** @module TenantsPage — Admin list page for managing tenant organizations. */
"use client";

import { Building2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { ErrorBanner } from "@/components/ui/error-banner";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteTenant, listTenants, type Tenant } from "@/lib/api";
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
    header: "Name",
    sortField: "name",
    filterField: "name",
    cell: (t) => (
      <Link
        href={`/admin/tenants/${t.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {t.name}
      </Link>
    ),
  },
  {
    header: "Slug",
    sortField: "slug",
    filterField: "slug",
    cell: (t) => t.slug,
  },
  {
    header: "Enabled",
    sortField: "enabled",
    filterField: "enabled",
    filterOp: "eq",
    filterOptions: BOOL_FILTER_OPTIONS,
    cell: (t) => (t.enabled ? "✓" : "—"),
  },
];

export default function TenantsPage() {
  const dispatch = useAppDispatch();
  const {
    rows,
    loading,
    refreshing,
    error,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload,
  } = useTableQuery<Tenant>(listTenants, {
    limit: LIMIT,
    errorMessage: "Failed to load tenants",
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteTenant(confirmTarget.id);
      setConfirmTarget(null);
      setActionError(null);
      dispatch(tenantsChanged());
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete tenant");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Tenant>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      cell: (tenant) => (
        <div className="flex gap-2">
          <DeleteIconButton onClick={() => handleDelete(tenant.id, tenant.name)} />
        </div>
      ),
    },
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tenants" }]} />
      <AdminPageHeader
        title="Tenants"
        icon={Building2}
        addHref="/admin/tenants/new"
        addLabel="+ Add tenant"
        onRefresh={reload}
        refreshing={loading || refreshing}
      />
      <div className="mb-4">
        <ErrorBanner error={actionError ?? error} />
      </div>
      <DataTable
        columns={columns}
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
