/** @module SecretsPage — Admin list page for managing registered secrets. */
"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { ErrorBanner } from "@/components/ui/error-banner";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteSecret, listSecrets, type Secret } from "@/lib/api";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<Secret>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    cell: (s) => (
      <Link
        href={`/admin/secrets/${s.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {s.name}
      </Link>
    ),
  },
  {
    header: "Type",
    sortField: "type",
    filterField: "type",
    cell: (s) => (s.type === "vault" ? "Vault" : "Local"),
  },
  {
    header: "Reference",
    cell: (s) =>
      s.type === "vault" ? (
        `${s.vaultMount}/${s.vaultPath} · ${s.vaultKey}`
      ) : (
        <span className="text-on-surface-variant">Encrypted value</span>
      ),
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
  },
];

export default function SecretsPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<Secret>(listSecrets, {
      limit: LIMIT,
      errorMessage: "Failed to load secrets",
    });
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteSecret(confirmTarget.id);
      setConfirmTarget(null);
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete secret");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Secret>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      cell: (secret) => (
        <div className="flex gap-2">
          <DeleteIconButton onClick={() => handleDelete(secret.id, secret.name)} />
        </div>
      ),
    },
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Secrets" }]} />
      <AdminPageHeader
        title="Secrets"
        icon={KeyRound}
        addHref="/admin/secrets/new"
        addLabel="+ Add secret"
        onRefresh={reload}
        refreshing={loading}
      />
      <div className="mb-4">
        <ErrorBanner error={actionError ?? error} />
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        emptyMessage="No secrets registered yet."
        emptyIcon={KeyRound}
        getRowKey={(secret) => secret.id}
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
        title="Delete Secret"
        description={
          confirmTarget
            ? `Delete "${confirmTarget.name}"? Anything still referencing it will fail at its next use.`
            : ""
        }
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
