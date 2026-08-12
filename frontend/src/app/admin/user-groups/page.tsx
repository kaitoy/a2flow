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
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteUserGroup, listUserGroups, type UserGroup } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { ROLE_LABELS, Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<UserGroup>[] = [
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
  {
    header: "Description",
    filterField: "description",
    cell: (g) => g.description || EMPTY_VALUE,
  },
  {
    // Roles are a JSON column, so they are display-only: the list API can
    // neither sort nor filter on them.
    header: "Roles",
    noTruncate: true,
    cell: (g) =>
      g.roles && g.roles.length > 0
        ? g.roles.map((role) => ROLE_LABELS[role]).join(", ")
        : EMPTY_VALUE,
  },
  {
    // Membership lives in a join table rather than on the group row, so this is
    // display-only too.
    header: "Members",
    className: "text-center",
    cell: (g) => g.memberIds?.length ?? 0,
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (g) => <DateTime value={g.createdAt} className="text-on-surface-variant" />,
  },
];

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
    ...STATIC_COLUMNS,
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
