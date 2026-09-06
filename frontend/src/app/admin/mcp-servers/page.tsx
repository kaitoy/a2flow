/**
 * @module McpServersPage — Admin list page for managing registered MCP servers.
 *
 * Reads are open to every authenticated user, so a viewer without the developer
 * role sees the list but none of the write entry points — Add, Browse registry,
 * and the per-row Delete — the same convention the detail page follows by
 * rendering read-only.
 */
"use client";

import { PackageSearch, Server } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { RegistrySearchDialog } from "@/components/admin/registry-search-dialog";
import { tagsColumn } from "@/components/admin/tag-columns";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import {
  deleteMcpServer,
  listMcpServers,
  type McpRegistryServerEntry,
  type McpServer,
} from "@/lib/api";
import { buildPrefillHref } from "@/lib/mcp-registry-prefill";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

function buildColumns(
  names: Map<string, string>,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<McpServer>[] {
  return [
    ...(isAllTenantsView ? [tenantColumn<McpServer>(tenantNames)] : []),
    idColumn<McpServer>(),
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (s) => (
        <Link
          href={`/admin/mcp-servers/${s.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.name}
        </Link>
      ),
    },
    {
      header: "Description",
      cell: (s) => s.description || "—",
    },
    {
      header: "Transport",
      sortField: "transport",
      filterField: "transport",
      className: "text-center",
      visibility: "optional",
      cell: (s) => <Badge>{s.transport === "stdio" ? "stdio" : "HTTP"}</Badge>,
    },
    {
      header: "Endpoint",
      sortField: "url",
      filterField: "url",
      className: "font-mono",
      cell: (s) => (s.transport === "stdio" ? [s.command, ...(s.args ?? [])].join(" ") : s.url),
    },
    {
      header: "Headers / Env",
      visibility: "optional",
      cell: (s) => {
        const count = Object.keys((s.transport === "stdio" ? s.env : s.headers) ?? {}).length;
        if (count === 0) return <span className="text-on-surface-variant">—</span>;
        const noun = s.transport === "stdio" ? "variable" : "header";
        return `${count} ${noun}${count === 1 ? "" : "s"}`;
      },
    },
    {
      header: "Created At",
      sortField: "createdAt",
      visibility: "optional",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    ...auditColumns<McpServer>(names),
  ];
}

export default function McpServersPage() {
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
  } = useTableQuery<McpServer>(listMcpServers, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const names = useUserNames(rows.flatMap((s) => [s.createdBy, s.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((s) => s.tenantId) : []);
  const router = useRouter();
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [registryOpen, setRegistryOpen] = useState(false);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  /** Close the registry dialog and open the create form pre-filled from the pick. */
  function handleRegistrySelect(entry: McpRegistryServerEntry) {
    setRegistryOpen(false);
    router.push(buildPrefillHref(entry));
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteMcpServer(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<McpServer>[] = [
    ...buildColumns(names, tenantNames, isAllTenantsView),
    tagsColumn<McpServer>((row) => row.tagIds, tagsById),
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (server: McpServer) => (
              <div className="flex justify-center gap-2">
                <DeleteIconButton onClick={() => handleDelete(server.id, server.name)} />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "mcpServers",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "MCP Servers" }]} />
      <AdminPageHeader
        title="MCP Servers"
        icon={Server}
        addHref={canEdit ? "/admin/mcp-servers/new" : undefined}
        addLabel="+ Add server"
        secondaryAction={
          // Browsing the registry only leads to the create form, so it is a
          // write entry point like Add.
          canEdit ? (
            <Button
              variant="secondary"
              className="inline-flex items-center gap-1.5"
              onClick={() => setRegistryOpen(true)}
            >
              <PackageSearch size={16} />
              Browse registry
            </Button>
          ) : undefined
        }
        columnPicker={
          <ColumnPicker
            options={options}
            value={selected}
            onChange={setSelected}
            onReset={reset}
            customized={customized}
          />
        }
        onRefresh={reload}
        refreshing={loading || refreshing}
      />
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage="No MCP servers registered yet."
        emptyIcon={Server}
        getRowKey={(server) => server.id}
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
        title="Delete MCP Server"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
      <RegistrySearchDialog
        open={registryOpen}
        onClose={() => setRegistryOpen(false)}
        onSelect={handleRegistrySelect}
      />
    </AdminPageContainer>
  );
}
