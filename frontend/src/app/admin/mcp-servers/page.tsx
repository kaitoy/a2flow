/** @module McpServersPage — Admin list page for managing registered MCP servers. */
"use client";

import Link from "next/link";
import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useTableQuery } from "@/hooks/useTableQuery";
import { deleteMcpServer, listMcpServers, type McpServer } from "@/lib/api";

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
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
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
        addHref="/admin/mcp-servers/new"
        addLabel="+ Add server"
      />
      <ErrorBanner error={actionError ?? error} />
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        emptyMessage="No MCP servers registered yet."
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
    </div>
  );
}
