/** @module UsersPage — Admin list page for managing application users. */
"use client";

import { Users as UsersIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { Avatar } from "@/components/ui/avatar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteUser, listUsers, type User } from "@/lib/api";

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
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<User>(listUsers, { limit: LIMIT, errorMessage: "Failed to load users" });
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteUser(confirmTarget.id);
      setConfirmTarget(null);
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete user");
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
          <button
            type="button"
            onClick={() => handleDelete(user.id, user.username)}
            className="cursor-pointer text-error transition-colors hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl p-8">
      <AdminPageHeader
        title="Users"
        icon={UsersIcon}
        addHref="/admin/users/new"
        addLabel="+ Add user"
        onRefresh={reload}
        refreshing={loading}
      />
      <ErrorBanner error={actionError ?? error} />
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
    </div>
  );
}
