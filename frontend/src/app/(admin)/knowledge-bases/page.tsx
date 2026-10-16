/**
 * @module KnowledgeBasesPage — Admin list page for the tenant's knowledge bases.
 *
 * A knowledge base is a wiki the LLM writes from registered web pages and
 * documents; workflows linked to it read it while they run. Writes need
 * `developer`; reads stay open, so a viewer without it sees the list but
 * neither the Add button nor the per-row Delete.
 */
"use client";

import { BookOpen } from "lucide-react";
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
import { tenantColumn } from "@/components/admin/tenant-columns";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTenantNames, useUserNames } from "@/hooks/useNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { deleteKnowledgeBase, type KnowledgeBase, listKnowledgeBases } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

/** Admin page listing the tenant's knowledge bases. */
export default function KnowledgeBasesPage() {
  const canEdit = useHasRole(Role.DEVELOPER);
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
  } = useTableQuery<KnowledgeBase>(listKnowledgeBases, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const names = useUserNames(rows.flatMap((kb) => [kb.createdBy, kb.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup is
  // super_admin-only, so asking as a plain admin would only come back 403.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((kb) => kb.tenantId) : []);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteKnowledgeBase(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<KnowledgeBase>[] = [
    ...(isAllTenantsView ? [tenantColumn<KnowledgeBase>(tenantNames)] : []),
    idColumn<KnowledgeBase>(),
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (kb) => (
        <Link
          href={`/knowledge-bases/${kb.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {kb.name}
        </Link>
      ),
    },
    {
      header: "Description",
      filterField: "description",
      cell: (kb) => kb.description || "—",
    },
    ...auditColumns<KnowledgeBase>(names),
    tagsColumn<KnowledgeBase>((row) => row.tagIds, tagsById),
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (kb: KnowledgeBase) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton onClick={() => setConfirmTarget({ id: kb.id, name: kb.name })} />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "knowledgeBases",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: "Knowledge Bases" }]} />
      <AdminPageHeader
        title="Knowledge Bases"
        icon={BookOpen}
        addHref={canEdit ? "/knowledge-bases/new" : undefined}
        addLabel="+ Add knowledge base"
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
        emptyMessage="No knowledge bases created yet."
        emptyIcon={BookOpen}
        getRowKey={(kb) => kb.id}
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
        title="Delete Knowledge Base"
        description={
          confirmTarget
            ? `Delete "${confirmTarget.name}" with all its sources and pages? Workflows linked to it lose access to it.`
            : ""
        }
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
