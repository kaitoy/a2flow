/**
 * @module McpToolMocksPage — Admin list page for the tenant's tool mocks.
 *
 * A mock stands in for one tool during a draft workflow run, returning a
 * configured result instead of calling it. Writes need `developer` (the same
 * role that registers MCP servers); reads stay open, so a viewer without it
 * sees the list but neither the Add button nor the per-row Delete.
 */
"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tagsColumn } from "@/components/admin/tag-columns";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { deleteMcpToolMock, listMcpServers, listMcpToolMocks, type McpToolMock } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;
/** Upper bound used to fetch the MCP server registry for the Server column. */
const SERVER_LIMIT = 1000;

function buildColumns(
  serverNameById: Map<string, string>,
  names: Map<string, string>,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<McpToolMock>[] {
  return [
    ...(isAllTenantsView ? [tenantColumn<McpToolMock>(tenantNames)] : []),
    idColumn<McpToolMock>(),
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (mock) => (
        <Link
          href={`/admin/mcp-tool-mocks/${mock.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {mock.name}
        </Link>
      ),
    },
    {
      header: "Tool",
      sortField: "toolName",
      filterField: "toolName",
      cell: (mock) => <span className="font-mono text-on-surface">{mock.toolName}</span>,
    },
    {
      header: "Server",
      noTruncate: true,
      cell: (mock) =>
        mock.mcpServerId ? (
          (serverNameById.get(mock.mcpServerId) ?? `${mock.mcpServerId.slice(0, 8)}…`)
        ) : (
          <Badge>Built-in</Badge>
        ),
    },
    {
      header: "Description",
      cell: (mock) => mock.description || "—",
    },
    {
      // How many successive calls the mock answers differently before its last
      // response starts repeating. Off by default: the count is a niche detail
      // most viewers do not need, so it is offered through the column picker.
      header: "Responses",
      visibility: "optional",
      className: "text-center",
      cell: (mock) => mock.responses.length,
    },
    ...auditColumns<McpToolMock>(names),
  ];
}

export default function McpToolMocksPage() {
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
  } = useTableQuery<McpToolMock>(listMcpToolMocks, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  const names = useUserNames(rows.flatMap((mock) => [mock.createdBy, mock.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((mock) => mock.tenantId) : []);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; the column falls back to truncated ids.
      });
  }, []);

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteMcpToolMock(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<McpToolMock>[] = [
    ...buildColumns(serverNameById, names, tenantNames, isAllTenantsView),
    tagsColumn<McpToolMock>((row) => row.tagIds, tagsById),
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (mock: McpToolMock) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton
                  onClick={() => setConfirmTarget({ id: mock.id, name: mock.name })}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "mcpToolMocks",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tool Mocks" }]} />
      <AdminPageHeader
        title="Tool Mocks"
        icon={FlaskConical}
        addHref={canEdit ? "/admin/mcp-tool-mocks/new" : undefined}
        addLabel="+ Add tool mock"
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
        emptyMessage="No tool mocks created yet."
        emptyIcon={FlaskConical}
        getRowKey={(mock) => mock.id}
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
        title="Delete Tool Mock"
        description={
          confirmTarget
            ? `Delete "${confirmTarget.name}"? Runs already started keep their own copy of it and are unaffected.`
            : ""
        }
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
