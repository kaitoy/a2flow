/**
 * @module UserGroupsPage — Admin list page for the tenant's user groups.
 *
 * A group grants its roles to every member, so managing roles by group is the
 * alternative to editing each account one at a time. Reads are open to every
 * authenticated user, so a viewer without the admin role sees the list but
 * neither the Add button nor the per-row Delete — the same convention the
 * detail page follows by rendering read-only.
 */
"use client";

import { UsersRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { USER_GROUP_SHARED_COLUMNS } from "@/components/admin/user-group-columns";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { deleteUserGroup, listUserGroups, type UserGroup } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

/**
 * Columns of the list table. Name and Created At are local to this page —
 * Name links off to the group's detail page, which the picker dialog never
 * does — the rest is shared with {@link GroupPicker}'s dialog table via
 * {@link USER_GROUP_SHARED_COLUMNS}.
 */
function buildColumns(
  names: Map<string, string>,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<UserGroup>[] {
  return [
    idColumn<UserGroup>(),
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (g) => (
        <Link
          href={`/admin/user-groups/${g.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {g.name}
        </Link>
      ),
    },
    ...USER_GROUP_SHARED_COLUMNS,
    {
      header: "Created At",
      sortField: "createdAt",
      visibility: "optional",
      cell: (g) => <DateTime value={g.createdAt} className="text-on-surface-variant" />,
    },
    ...(isAllTenantsView ? [tenantColumn<UserGroup>(tenantNames)] : []),
    ...auditColumns<UserGroup>(names),
  ];
}

export default function UserGroupsPage() {
  const canEdit = useHasRole(Role.ADMIN);
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
  } = useTableQuery<UserGroup>(listUserGroups, { limit: LIMIT });
  const names = useUserNames(rows.flatMap((g) => [g.createdBy, g.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((g) => g.tenantId) : []);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteUserGroup(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<UserGroup>[] = [
    ...buildColumns(names, tenantNames, isAllTenantsView),
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (group: UserGroup) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton
                  onClick={() => setConfirmTarget({ id: group.id, name: group.name })}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "user-groups",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "User Groups" }]} />
      <AdminPageHeader
        title="User Groups"
        icon={UsersRound}
        addHref={canEdit ? "/admin/user-groups/new" : undefined}
        addLabel="+ Add group"
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
        emptyMessage="No user groups created yet."
        emptyIcon={UsersRound}
        getRowKey={(group) => group.id}
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
        title="Delete User Group"
        description={
          confirmTarget
            ? `Delete "${confirmTarget.name}"? Its members keep their accounts but lose the roles it grants.`
            : ""
        }
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
