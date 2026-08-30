/**
 * @module McpServerPickerDialog — {@link RecordPickerDialog} configured to pick
 * one registered MCP server.
 *
 * Its own module rather than a private of {@link import("./mcp-tool-picker").McpToolPicker}:
 * both that multi-select picker and the single-select
 * {@link import("./mcp-tool-field").McpToolField} open the same dialog, so its
 * column set — and the `useTags` call behind the Tags column — live in one place.
 */
"use client";

import { Server } from "lucide-react";
import { RecordPickerDialog } from "@/components/admin/record-picker-dialog";
import { tagsColumn } from "@/components/admin/tag-columns";
import type { ColumnDef } from "@/components/ui/data-table";
import { useTags } from "@/hooks/useTags";
import { listMcpServers, type McpServer } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Props for {@link McpServerPickerDialog}. */
export interface McpServerPickerDialogProps {
  open: boolean;
  onClose: () => void;
  /** Called with the chosen server's id and name, or `("", "")` if cleared. */
  onAssign: (id: string, name: string) => void;
  panelId: string;
  /** Currently chosen server id, or `""` when none is chosen. */
  value: string;
}

/**
 * {@link RecordPickerDialog} configured for MCP servers, columned like the MCP
 * Servers list page minus the columns that don't help a picker: the name is
 * plain text rather than a link (this dialog does not navigate away from a
 * half-filled form), and the id, audit, and action columns describe bookkeeping
 * the operator is not picking on. Endpoint stays because it is what tells two
 * similarly named servers apart, and Tags stays and is filterable, since tags
 * are how a tenant with many servers narrows down to the one it wants.
 *
 * A component of its own, not inlined into its callers, so `useTags` — like
 * {@link RecordPickerDialog}'s own row fetch — only runs once the picker has
 * actually been opened, not on every mount of the field.
 */
export function McpServerPickerDialog({
  open,
  onClose,
  onAssign,
  panelId,
  value,
}: McpServerPickerDialogProps) {
  const { byId: tagsById } = useTags();
  const columns: ColumnDef<McpServer>[] = [
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (server) => server.name,
    },
    {
      header: "Description",
      cell: (server) => server.description || EMPTY_VALUE,
    },
    {
      header: "Endpoint",
      sortField: "url",
      filterField: "url",
      className: "font-mono",
      cell: (server) =>
        server.transport === "stdio"
          ? [server.command, ...(server.args ?? [])].join(" ")
          : server.url,
    },
    tagsColumn<McpServer>((server) => server.tagIds, tagsById),
  ];

  return (
    <RecordPickerDialog<McpServer>
      open={open}
      onClose={onClose}
      onAssign={(ids, options) => onAssign(ids[0] ?? "", options[0]?.label ?? "")}
      panelId={panelId}
      title="Select MCP server"
      value={value === "" ? [] : [value]}
      multiple={false}
      listRecords={listMcpServers}
      columns={columns}
      getId={(server) => server.id}
      getLabel={(server) => server.name}
      emptyMessage="This tenant has no MCP servers yet."
      emptyIcon={Server}
    />
  );
}
