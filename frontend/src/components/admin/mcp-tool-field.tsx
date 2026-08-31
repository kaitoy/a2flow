/**
 * @module McpToolField — Two-step picker for one MCP server tool.
 *
 * The single-select sibling of {@link McpToolPicker}: that one gathers a list of
 * `(server, tool)` pairs as chips; this one holds exactly one pair, as two
 * separate values (`mcpServerId`, `toolName`). Used by the tool-mock form, whose
 * `mcp` target names one tool of one server.
 *
 * The shape follows {@link SecretRefField} and {@link McpToolPicker}: pick the
 * server from a {@link McpServerPickerDialog} (which pages and filters
 * server-side), then pick the tool from the server's live listing
 * ({@link useMcpServerTools}). Nothing connects to a server until one is picked;
 * the mount cost is a single registry read, used to name the chosen server and
 * to tell "no servers registered" apart from "registry read failed".
 *
 * A stored `toolName` the server no longer advertises — or that cannot be listed
 * because the server is unreachable — is kept and shown, labelled `(not found)`
 * when the listing positively lacks it. `value` alone is authoritative; clearing
 * it is the operator's call.
 */
"use client";

import { Server } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { McpServerPickerDialog } from "@/components/admin/mcp-server-picker-dialog";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, type SelectOption } from "@/components/ui/select";
import { type UseMcpServerToolsResult, useMcpServerTools } from "@/hooks/useMcpServerTools";
import { getApiErrorMessage, listMcpServers } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Upper bound used to read the whole MCP server registry for the name map. */
const SERVER_LIMIT = 1000;

/** What the one-off registry read is currently doing. */
type RegistryState =
  | { phase: "loading" }
  | { phase: "ready"; names: Map<string, string> }
  | { phase: "error"; message: string };

/** The `(server, tool)` pair this field edits. */
export interface McpToolSelection {
  /** Chosen server id, or `""` when none is chosen. */
  mcpServerId: string;
  /** Chosen tool name, or `""` when none is chosen. */
  toolName: string;
}

/** Props for {@link McpToolField}. */
export interface McpToolFieldProps extends McpToolSelection {
  /**
   * Called with the next pair. Choosing a different server clears the tool;
   * removing the server clears both.
   */
  onChange: (next: McpToolSelection) => void;
  /** Prefix for the tool select's DOM id and the dialog's panel id. */
  idPrefix: string;
  /** Validation message for the server, shown under the server chip/button. */
  serverError?: string;
  /** Validation message for the tool, shown under the tool select. */
  toolError?: string;
  /** Render the chosen pair as plain text, with no controls. */
  readOnly?: boolean;
  /**
   * A listing the caller already holds, used instead of fetching one here.
   *
   * Listing a server means connecting to it live — a `stdio` server can take a
   * minute — so a caller that needs the same listing for something else of its
   * own (the tool-mock form reads the chosen tool's declared output format)
   * owns one {@link useMcpServerTools} and passes it in rather than causing a
   * second connection.
   */
  tools?: UseMcpServerToolsResult;
}

/**
 * Controlled picker for one MCP server tool.
 *
 * Reads the server registry once on mount — a plain database listing, no MCP
 * connection — to name the chosen server and to tell "no servers registered"
 * apart from "registry read failed". The chosen server's tools are fetched on
 * demand; a read-only rendering skips that live query entirely.
 */
export function McpToolField({
  mcpServerId,
  toolName,
  onChange,
  idPrefix,
  serverError,
  toolError,
  readOnly = false,
  tools: providedTools,
}: McpToolFieldProps) {
  const [registry, setRegistry] = useState<RegistryState>({ phase: "loading" });
  // Holds the name the dialog last reported, so the chip has a label before the
  // registry read lands — and the only label when that read failed.
  const [pickedName, setPickedName] = useState("");
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);

  // Guards the post-await state update. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadRegistry = useCallback(async () => {
    setRegistry({ phase: "loading" });
    try {
      const servers = await listMcpServers({ limit: SERVER_LIMIT });
      if (!mountedRef.current) return;
      setRegistry({ phase: "ready", names: new Map(servers.map((s) => [s.id, s.name])) });
    } catch (err) {
      if (mountedRef.current) setRegistry({ phase: "error", message: getApiErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  // No live connection behind a read-only rendering: it shows the stored tool
  // name as text and never offers the listing. Nor behind a caller-owned
  // listing — the hook is still called unconditionally (it is a hook), just
  // told to fetch nothing.
  const ownTools = useMcpServerTools(
    readOnly || providedTools !== undefined || mcpServerId === "" ? null : mcpServerId
  );
  const { state: tools, reload: reloadTools } = providedTools ?? ownTools;

  const registryName = registry.phase === "ready" ? registry.names.get(mcpServerId) : undefined;
  const serverLabel = registryName ?? (pickedName !== "" ? pickedName : mcpServerId);

  const toolNames = tools.phase === "ready" ? tools.tools.map((tool) => tool.name) : [];
  const toolUnlisted = toolName !== "" && !toolNames.includes(toolName);
  // The listing loaded and positively lacks it — as opposed to not having
  // loaded yet, or having failed.
  const toolMissing = toolUnlisted && tools.phase === "ready";

  // The select's placeholder carries the state: an empty dropdown alone cannot
  // say whether the server is slow, silent, or unreachable.
  let placeholder = "Select a tool…";
  let toolsDisabled = false;
  if (tools.phase === "idle" || tools.phase === "loading") {
    placeholder = "Loading tools…";
    toolsDisabled = true;
  } else if (tools.phase === "error") {
    placeholder = "Could not load tools";
    toolsDisabled = true;
  } else if (toolNames.length === 0) {
    placeholder = "No tools advertised";
    toolsDisabled = true;
  }
  // A stored value that isn't in the listing must still be selectable — if only
  // so the operator can clear it — whatever state the listing is in.
  if (toolUnlisted) toolsDisabled = false;

  const toolOptions: SelectOption[] = [
    { value: "", label: toolName === "" ? placeholder : "None" },
    ...(toolUnlisted
      ? [{ value: toolName, label: toolMissing ? `${toolName} (not found)` : toolName }]
      : []),
    ...toolNames.map((name) => ({ value: name, label: name })),
  ];

  /** Apply a newly chosen server, dropping any tool chosen under the old one. */
  function handleServer(id: string, name: string) {
    setPickedName(id === "" ? "" : name);
    onChange({ mcpServerId: id, toolName: id === mcpServerId ? toolName : "" });
  }

  /** Opens the picker dialog, mounting it on the first call. */
  function openPicker() {
    setEverOpened(true);
    setOpen(true);
  }

  if (readOnly) {
    return (
      <>
        <div className="flex flex-col gap-1.5">
          <span className="text-label-caps">MCP Server</span>
          <ReadOnlyField>{serverLabel || EMPTY_VALUE}</ReadOnlyField>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-label-caps">Tool Name</span>
          <ReadOnlyField>{toolName || EMPTY_VALUE}</ReadOnlyField>
        </div>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {registry.phase === "loading" && (
        <div className="rounded-xl glass-panel px-4 py-3">
          <EmptyState
            icon={Server}
            compact
            title="Loading MCP servers…"
            description="Reading the registered servers."
          />
        </div>
      )}

      {registry.phase === "error" && (
        <div className="flex flex-col items-start gap-2 rounded-xl glass-panel px-4 py-3">
          <p className="text-sm text-on-surface-variant">Could not load the MCP server registry.</p>
          <p className="text-xs text-error">{registry.message}</p>
          <Button type="button" variant="secondary" onClick={() => void loadRegistry()}>
            Retry
          </Button>
        </div>
      )}

      {registry.phase === "ready" &&
        (registry.names.size === 0 && mcpServerId === "" ? (
          <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
            No MCP servers are registered.{" "}
            <Link
              href="/admin/mcp-servers"
              className="text-accent transition-colors hover:underline"
            >
              Register one
            </Link>{" "}
            to point this mock at one of its tools.
          </p>
        ) : mcpServerId === "" ? (
          // Nothing is chosen yet, so there is nothing for the Tool select to
          // offer either. Collapse to the one control that does something,
          // exactly as `SecretRefField` and `McpToolPicker` do.
          <div className="flex flex-col gap-1.5">
            <span className="text-label-caps">MCP Server</span>
            <div>
              <Button type="button" variant="secondary" onClick={openPicker}>
                Select MCP server…
              </Button>
            </div>
            {serverError && <p className="text-xs text-error">{serverError}</p>}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Deliberately not a FormField: its `<label htmlFor>` would become
                the accessible name of the "Select MCP server…" button. */}
            <div className="flex flex-col gap-1.5">
              <span className="text-label-caps">MCP Server</span>
              <div className="flex flex-wrap gap-1.5">
                <Chip label={serverLabel} onRemove={() => handleServer("", "")} size="lg" />
              </div>
              <div>
                <Button type="button" variant="secondary" onClick={openPicker}>
                  Select MCP server…
                </Button>
              </div>
              {serverError && <p className="text-xs text-error">{serverError}</p>}
            </div>
            <FormField htmlFor={`${idPrefix}Tool`} label="Tool Name" error={toolError}>
              <Select
                id={`${idPrefix}Tool`}
                options={toolOptions}
                value={toolName}
                onChange={(next) => onChange({ mcpServerId, toolName: next })}
                disabled={toolsDisabled}
              />
              {tools.phase === "error" && (
                <div className="flex flex-col items-start gap-1.5">
                  <p className="text-xs text-error">{tools.message}</p>
                  <Button type="button" variant="secondary" onClick={reloadTools}>
                    Retry
                  </Button>
                </div>
              )}
            </FormField>
          </div>
        ))}

      {/* Mounted on the first open and then kept mounted, so the server list
          costs nothing until asked for and the leave animation still has a
          component to run on. */}
      {everOpened && (
        <McpServerPickerDialog
          open={open}
          onClose={() => setOpen(false)}
          onAssign={(id, name) => {
            handleServer(id, name);
            setOpen(false);
          }}
          panelId={`${idPrefix}-server-picker-dialog`}
          value={mcpServerId}
        />
      )}
    </div>
  );
}
