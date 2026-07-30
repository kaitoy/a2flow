/** @module SecretsPage — Admin list page for managing registered secrets. */
"use client";

import { KeyRound } from "lucide-react";
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
import { deleteSecret, listSecrets, type Secret } from "@/lib/api";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<Secret>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    visibility: "always",
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
    visibility: "optional",
    cell: (s) =>
      s.type === "vault" ? (
        `${s.vaultMount}/${s.vaultPath}`
      ) : (
        <span className="text-on-surface-variant">
          {(s.keys ?? []).length === 1 ? "1 entry" : `${(s.keys ?? []).length} entries`}
        </span>
      ),
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
  },
];

export default function SecretsPage() {
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
  } = useTableQuery<Secret>(listSecrets, { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteSecret(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Secret>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (secret) => (
        <div className="flex justify-center gap-2">
          <DeleteIconButton onClick={() => handleDelete(secret.id, secret.name)} />
        </div>
      ),
    },
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "secrets",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Secrets" }]} />
      <AdminPageHeader
        title="Secrets"
        icon={KeyRound}
        addHref="/admin/secrets/new"
        addLabel="+ Add secret"
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
