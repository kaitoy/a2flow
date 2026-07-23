/** @module UsersPage — Admin list page for managing application users. */
"use client";

import { Users as UsersIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteUser, listUsers, type User } from "@/lib/api";
import { ROLE_LABELS, Role } from "@/lib/roles";

const LIMIT = 20;

/** Yes/No options for the boolean `eq` column filters. */
const BOOL_FILTER_OPTIONS = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
];

/** Render a boolean cell as a checkmark or an em dash. */
function boolCell(value: boolean): string {
  return value ? "✓" : "—";
}

const STATIC_COLUMNS: ColumnDef<User>[] = [
  {
    header: "",
    noTruncate: true,
    cell: (u) => <Avatar user={u} size={28} />,
  },
  {
    header: "Username",
    sortField: "username",
    filterField: "username",
    cell: (u) => (
      <Link
        href={`/admin/users/${u.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {u.username}
      </Link>
    ),
  },
  {
    header: "Name",
    sortField: "firstName",
    filterField: "firstName",
    cell: (u) => `${u.firstName} ${u.lastName}`,
  },
  {
    header: "Email",
    sortField: "email",
    filterField: "email",
    cell: (u) => u.email,
  },
  {
    // Roles are stored as a JSON list, which the list API's sort/filter params
    // cannot address, so this column is display-only. The Super Admin badge is
    // a chip, not plain text, so it opts out of single-line truncation.
    header: "Roles",
    noTruncate: true,
    cell: (u) => {
      const isSuperAdmin = u.roles?.includes(Role.SUPER_ADMIN);
      const otherRoles = (u.roles ?? []).filter((r) => r !== Role.SUPER_ADMIN);
      return (
        <div className="flex items-center gap-1.5">
          {isSuperAdmin && <Badge>Super Admin</Badge>}
          {otherRoles.length > 0 && <span>{otherRoles.map((r) => ROLE_LABELS[r]).join(", ")}</span>}
          {!isSuperAdmin && otherRoles.length === 0 && "—"}
        </div>
      );
    },
  },
  {
    header: "Enabled",
    sortField: "enabled",
    filterField: "enabled",
    filterOp: "eq",
    filterOptions: BOOL_FILTER_OPTIONS,
    cell: (u) => boolCell(u.enabled),
  },
  {
    header: "Verified",
    sortField: "emailVerified",
    filterField: "emailVerified",
    filterOp: "eq",
    filterOptions: BOOL_FILTER_OPTIONS,
    cell: (u) => boolCell(u.emailVerified),
  },
];

export default function UsersPage() {
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
  } = useTableQuery<User>(listUsers, { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteUser(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<User>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      cell: (user) => (
        <div className="flex gap-2">
          <DeleteIconButton onClick={() => handleDelete(user.id, user.username)} />
        </div>
      ),
    },
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Users" }]} />
      <AdminPageHeader
        title="Users"
        icon={UsersIcon}
        addHref="/admin/users/new"
        addLabel="+ Add user"
        onRefresh={reload}
        refreshing={loading || refreshing}
      />
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        emptyMessage="No users registered yet."
        emptyIcon={UsersIcon}
        getRowKey={(user) => user.id}
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
        title="Delete User"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
