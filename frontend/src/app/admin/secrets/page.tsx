/**
 * @module SecretsPage — Admin list page for managing registered secrets.
 *
 * Reads are open to every authenticated user, so a viewer without the admin
 * role sees the list but neither the Add button nor the per-row Delete — the
 * same convention the detail page follows by rendering read-only.
 */
"use client";

import { KeyRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tagsColumn } from "@/components/admin/tag-columns";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useUserNames } from "@/hooks/useUserNames";
import { deleteSecret, listSecrets, type Secret } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

function buildColumns(names: Map<string, string>): ColumnDef<Secret>[] {
  return [
    idColumn<Secret>(),
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
    ...auditColumns<Secret>(names),
  ];
}

export default function SecretsPage() {
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
    tagIds,
    setTagIds,
    reload,
  } = useTableQuery<Secret>(listSecrets, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const names = useUserNames(rows.flatMap((s) => [s.createdBy, s.updatedBy]));
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
    ...buildColumns(names),
    tagsColumn<Secret>((row) => row.tagIds, tagsById),
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (secret: Secret) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton onClick={() => handleDelete(secret.id, secret.name)} />
              </div>
            ),
          },
        ]
      : []),
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
        addHref={canEdit ? "/admin/secrets/new" : undefined}
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
        tagIds={tagIds}
        onTagIdsChange={setTagIds}
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
