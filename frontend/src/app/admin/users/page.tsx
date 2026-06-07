/** @module UsersPage — Admin list page for managing application users. */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { deleteUser, listUsers, type User } from "@/lib/api";

const LIMIT = 20;

/** Render a boolean cell as a checkmark or an em dash. */
function boolCell(value: boolean): string {
  return value ? "✓" : "—";
}

const STATIC_COLUMNS: ColumnDef<User>[] = [
  {
    header: "Username",
    cell: (u) => <span className="font-medium">{u.username}</span>,
  },
  {
    header: "Name",
    cell: (u) => `${u.firstName} ${u.lastName}`,
  },
  {
    header: "Email",
    className: "max-w-[220px] truncate",
    cell: (u) => u.email,
  },
  {
    header: "Enabled",
    cell: (u) => boolCell(u.enabled),
  },
  {
    header: "Verified",
    cell: (u) => boolCell(u.emailVerified),
  },
];

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listUsers(LIMIT, offset);
      setUsers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteUser(confirmTarget.id);
      setConfirmTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete user");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<User>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      cell: (user) => (
        <div className="flex gap-2">
          <Link
            href={`/admin/users/${user.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Edit
          </Link>
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
      <AdminPageHeader title="Users" addHref="/admin/users/new" addLabel="+ Add user" />
      <ErrorBanner error={error} />
      <DataTable
        columns={columns}
        rows={users}
        loading={loading}
        emptyMessage="No users registered yet."
        getRowKey={(user) => user.id}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={users.length}
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
