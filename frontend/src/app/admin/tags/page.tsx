/**
 * @module TagsPage — Admin list page for the tenant's tags.
 *
 * Tags are the label vocabulary the taggable resources draw from, so this page
 * is where the vocabulary itself is curated — attaching a tag happens on the
 * record. Writes need `admin` or `developer` (secrets are administered by the
 * former, MCP servers / skills / workflows by the latter, and both need to be
 * able to mint a label); reads stay open, so a viewer with neither role sees
 * the list but neither the Add button nor the per-row Delete.
 */
"use client";

import { Tags } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { Chip } from "@/components/ui/chip";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteTag, listTags, type Tag } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { resolveTagColor, tagColorLabel } from "@/lib/tag-palette";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<Tag>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    visibility: "always",
    cell: (tag) => (
      <Link
        href={`/admin/tags/${tag.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {tag.name}
      </Link>
    ),
  },
  {
    header: "Preview",
    // The chip is what a tag looks like everywhere else, so the list shows the
    // real thing rather than naming a color the reader has to imagine.
    noTruncate: true,
    cell: (tag) => <Chip label={tag.name} color={resolveTagColor(tag.color)} />,
  },
  {
    header: "Color",
    sortField: "color",
    visibility: "optional",
    cell: (tag) => (
      <span className="text-on-surface-variant">{tagColorLabel(resolveTagColor(tag.color))}</span>
    ),
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (tag) => <DateTime value={tag.createdAt} className="text-on-surface-variant" />,
  },
  ...auditColumns<Tag>(),
];

export default function TagsPage() {
  const canEdit = useHasRole(Role.ADMIN, Role.DEVELOPER);
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
  } = useTableQuery<Tag>(listTags, { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteTag(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Tag>[] = [
    ...STATIC_COLUMNS,
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (tag: Tag) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton
                  onClick={() => setConfirmTarget({ id: tag.id, name: tag.name })}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "tags",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tags" }]} />
      <AdminPageHeader
        title="Tags"
        icon={Tags}
        addHref={canEdit ? "/admin/tags/new" : undefined}
        addLabel="+ Add tag"
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
        emptyMessage="No tags created yet."
        emptyIcon={Tags}
        getRowKey={(tag) => tag.id}
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
        title="Delete Tag"
        description={
          confirmTarget
            ? `Delete "${confirmTarget.name}"? It is removed from every record currently carrying it.`
            : ""
        }
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
