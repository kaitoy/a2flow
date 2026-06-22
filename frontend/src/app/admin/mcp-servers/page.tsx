/** @module McpServersPage — Admin list page for managing registered MCP servers. */
"use client";

import { PackageSearch, Server } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { RegistrySearchDialog } from "@/components/admin/registry-search-dialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useTableQuery } from "@/hooks/useTableQuery";
import {
  deleteMcpServer,
  listMcpServers,
  type McpRegistryServerEntry,
  type McpServer,
} from "@/lib/api";
import { buildPrefillHref } from "@/lib/mcp-registry-prefill";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<McpServer>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    cell: (s) => <span className="font-medium">{s.name}</span>,
  },
  {
    header: "URL",
    sortField: "url",
    filterField: "url",
    cell: (s) => s.url,
  },
  {
    header: "Headers",
    cell: (s) => {
      const count = Object.keys(s.headers ?? {}).length;
      return count === 0 ? (
        <span className="text-on-surface-variant">—</span>
      ) : (
        `${count} header${count === 1 ? "" : "s"}`
      );
    },
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
  },
];

export default function McpServersPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<McpServer>(listMcpServers, {
      limit: LIMIT,
      errorMessage: "Failed to load MCP servers",
    });
  const router = useRouter();
  const [actionError, setActionError] = useState<string | null>(null);
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
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete MCP server");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<McpServer>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      cell: (server) => (
        <div className="flex gap-2">
          <Link
            href={`/admin/mcp-servers/${server.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Edit
          </Link>
          <button
            type="button"
            onClick={() => handleDelete(server.id, server.name)}
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
        title="MCP Servers"
        icon={Server}
        addHref="/admin/mcp-servers/new"
        addLabel="+ Add server"
        secondaryAction={
          <Button
            variant="secondary"
            className="inline-flex items-center gap-1.5"
            onClick={() => setRegistryOpen(true)}
          >
            <PackageSearch size={16} />
            Browse registry
          </Button>
        }
        onRefresh={reload}
        refreshing={loading}
      />
      <ErrorBanner error={actionError ?? error} />
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        emptyMessage="No MCP servers registered yet."
        emptyIcon={Server}
        getRowKey={(server) => server.id}
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
    </div>
  );
}
