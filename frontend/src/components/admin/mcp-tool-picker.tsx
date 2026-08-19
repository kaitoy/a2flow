/**
 * @module McpToolPicker — Two-step picker for binding MCP tools to a workflow task.
 *
 * Shared by the create and edit task-template forms so the two stay in step,
 * mirroring how {@link McpServerFields} is shared between the MCP server forms.
 *
 * The shape follows {@link SecretRefField}: choose the container first, then the
 * entry within it. That is not only a consistency argument — listing a server's
 * tools means A2Flow *connects to it live*, and a `stdio` server spawns a
 * subprocess that can take a minute to come up. A picker that offered every
 * server's tools in one list had to fan those connections out on mount and made
 * the operator wait for the slowest one before showing anything. Here the mount
 * cost is a single registry read, and a server is queried only once it has
 * actually been picked.
 *
 * The server side is a {@link RecordPickerDialog} rather than a second select
 * for the same reason the secret side is: it pages, sorts, and filters
 * server-side, so it stays usable however many servers a tenant registers.
 *
 * Bindings accumulate as chips rather than as a checked list, so tools from
 * several servers can be gathered without the picker having to hold every
 * server's catalog at once. A chip is always removable — including one whose
 * server is unreachable or which the server no longer advertises — since
 * `value` alone is authoritative and needs no live option to stay visible.
 */
"use client";

import { Server } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { RecordPickerDialog } from "@/components/admin/record-picker-dialog";
import { tagsColumn } from "@/components/admin/tag-columns";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import type { ColumnDef } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, type SelectOption } from "@/components/ui/select";
import { useTags } from "@/hooks/useTags";
import { getApiErrorMessage, listMcpServers, listMcpServerTools, type McpServer } from "@/lib/api";
import { bindingLabel, bindingToValue, valueToBinding } from "@/lib/mcp-tool-options";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Upper bound used to read the whole MCP server registry for the name map. */
const SERVER_LIMIT = 1000;

/** DOM id of the tool select, and the prefix of the dialog's panel id. */
const ID_PREFIX = "mcpTool";

/** Props for {@link McpServerPickerDialog}. */
interface McpServerPickerDialogProps {
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
 * A component of its own, not inlined into {@link McpToolPicker}, so `useTags` —
 * like {@link RecordPickerDialog}'s own row fetch — only runs once the picker
 * has actually been opened, not on every mount of the field.
 */
function McpServerPickerDialog({
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

/** What the one-off registry read is currently doing. */
type RegistryState =
  | { phase: "loading" }
  | { phase: "ready"; names: Map<string, string> }
  | { phase: "error"; message: string };

/** What the chosen server's live tool listing is currently doing. */
type ToolsState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ready"; names: string[] }
  | { phase: "error"; message: string };

/** Props for {@link McpToolPicker}. */
export interface McpToolPickerProps {
  /** Selected composite values (`<serverId>::<toolName>`). */
  value: string[];
  /** Called with the next selection whenever a tool is added or removed. */
  onChange: (next: string[]) => void;
}

/**
 * Controlled multi-select over MCP tools, gathered one server at a time.
 *
 * Reads the server registry once on mount — a plain database listing, with no
 * MCP connection behind it — both to label already-bound tools and to tell "no
 * servers are registered" apart from "the registry could not be read". The
 * chosen server's tools are then fetched on demand, and that fetch's four
 * outcomes (in flight, none advertised, all already added, unreachable) each
 * name themselves in the select rather than all collapsing into an empty
 * dropdown.
 */
export function McpToolPicker({ value, onChange }: McpToolPickerProps) {
  const [registry, setRegistry] = useState<RegistryState>({ phase: "loading" });
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(null);
  const [tools, setTools] = useState<ToolsState>({ phase: "idle" });
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);

  // Guards the post-await state updates. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Identifies the in-flight tool request. A `stdio` server can take a minute
  // to answer, which is long enough for the operator to have picked a different
  // server in the meantime — without this the slow reply would land on top of
  // the new server's tools.
  const toolsRequestRef = useRef(0);

  // Stable, so the effects below run once per input and the retry buttons can
  // reuse them.
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

  const loadTools = useCallback(async (serverId: string) => {
    const token = toolsRequestRef.current + 1;
    toolsRequestRef.current = token;
    setTools({ phase: "loading" });
    try {
      const fetched = await listMcpServerTools(serverId);
      if (!mountedRef.current || toolsRequestRef.current !== token) return;
      setTools({ phase: "ready", names: fetched.map((tool) => tool.name) });
    } catch (err) {
      if (!mountedRef.current || toolsRequestRef.current !== token) return;
      setTools({ phase: "error", message: getApiErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  const pickedId = picked?.id ?? null;
  useEffect(() => {
    if (pickedId === null) {
      // Abandon whatever is in flight, so a slow reply for the server just
      // cleared cannot repopulate the select after the fact.
      toolsRequestRef.current += 1;
      setTools({ phase: "idle" });
      return;
    }
    void loadTools(pickedId);
  }, [pickedId, loadTools]);

  // Names known from the registry, plus the one the dialog just reported —
  // which is the only source when the registry read itself failed.
  const serverNames = useMemo(() => {
    const names = new Map(registry.phase === "ready" ? registry.names : []);
    if (picked) names.set(picked.id, picked.name);
    return names;
  }, [registry, picked]);

  const chips = useMemo(
    () => value.map((v) => ({ value: v, label: bindingLabel(valueToBinding(v), serverNames) })),
    [value, serverNames]
  );

  // Tools of the chosen server that are already bound, so the select only ever
  // offers a pick that actually adds something.
  const alreadyAdded = useMemo(() => {
    if (pickedId === null) return new Set<string>();
    return new Set(
      value
        .map(valueToBinding)
        .filter((binding) => binding.mcpServerId === pickedId)
        .map((binding) => binding.toolName)
    );
  }, [value, pickedId]);

  const available =
    tools.phase === "ready" ? tools.names.filter((name) => !alreadyAdded.has(name)) : [];

  // The select's placeholder carries the state: an empty dropdown alone cannot
  // say whether the server is slow, silent, exhausted, or unreachable.
  let placeholder = "Select a tool…";
  let toolsDisabled = false;
  if (tools.phase === "idle" || tools.phase === "loading") {
    placeholder = "Loading tools…";
    toolsDisabled = true;
  } else if (tools.phase === "error") {
    placeholder = "Could not load tools";
    toolsDisabled = true;
  } else if (tools.names.length === 0) {
    placeholder = "No tools advertised";
    toolsDisabled = true;
  } else if (available.length === 0) {
    placeholder = "All tools added";
    toolsDisabled = true;
  }

  const toolOptions: SelectOption[] = [
    { value: "", label: placeholder },
    ...available.map((name) => ({ value: name, label: name })),
  ];

  /** Append the chosen tool. The select is an add action, so it holds no value. */
  function addTool(toolName: string) {
    if (toolName === "" || picked === null) return;
    onChange([...value, bindingToValue({ mcpServerId: picked.id, toolName })]);
  }

  /** Drop one binding, whether or not its server is still reachable. */
  function removeTool(composite: string) {
    onChange(value.filter((v) => v !== composite));
  }

  /** Opens the picker dialog, mounting it on the first call. */
  function openPicker() {
    setEverOpened(true);
    setOpen(true);
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
        (registry.names.size === 0 ? (
          <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
            No MCP servers are registered.{" "}
            <Link
              href="/admin/mcp-servers"
              className="text-accent transition-colors hover:underline"
            >
              Register one
            </Link>{" "}
            to bind its tools to this task.
          </p>
        ) : picked === null ? (
          // Nothing is chosen yet, so there is nothing for the Tool select to
          // offer either — showing it disabled next to an empty placeholder
          // just doubles the empty state. Collapse to the one control that
          // actually does something, exactly as `SecretRefField` does.
          <div className="flex flex-col gap-1.5">
            <span className="text-label-caps">MCP Server</span>
            <div>
              <Button type="button" variant="secondary" onClick={openPicker}>
                Select MCP server…
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Deliberately not a FormField: its `<label htmlFor>` would become
                the accessible name of whatever it points at, renaming the
                "Select MCP server…" button to the field's label. */}
            <div className="flex flex-col gap-1.5">
              <span className="text-label-caps">MCP Server</span>
              <div className="flex flex-wrap gap-1.5">
                <Chip label={picked.name} onRemove={() => setPicked(null)} size="lg" />
              </div>
              <div>
                <Button type="button" variant="secondary" onClick={openPicker}>
                  Select MCP server…
                </Button>
              </div>
            </div>
            <FormField htmlFor={ID_PREFIX} label="Tool">
              <Select
                id={ID_PREFIX}
                options={toolOptions}
                value=""
                onChange={addTool}
                disabled={toolsDisabled}
              />
              {tools.phase === "error" && (
                <div className="flex flex-col items-start gap-1.5">
                  <p className="text-xs text-error">{tools.message}</p>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void loadTools(picked.id)}
                  >
                    Retry
                  </Button>
                </div>
              )}
            </FormField>
          </div>
        ))}

      <div className="flex flex-col gap-1.5">
        <span className="text-label-caps">Selected Tools</span>
        {chips.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No tools are bound to this task yet.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <Chip
                key={chip.value}
                label={chip.label}
                onRemove={() => removeTool(chip.value)}
                size="lg"
              />
            ))}
          </div>
        )}
      </div>

      {/* Mounted on the first open and then kept mounted, so the server list
          costs nothing until asked for and the leave animation still has a
          component to run on. */}
      {everOpened && (
        <McpServerPickerDialog
          open={open}
          onClose={() => setOpen(false)}
          onAssign={(id, name) => {
            setPicked(id === "" ? null : { id, name });
            setOpen(false);
          }}
          panelId={`${ID_PREFIX}-server-picker-dialog`}
          value={pickedId ?? ""}
        />
      )}
    </div>
  );
}
