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
 * actually been picked (via {@link useMcpServerTools}).
 *
 * The server side is a {@link McpServerPickerDialog} rather than a second select
 * for the same reason the secret side is: it pages, sorts, and filters
 * server-side, so it stays usable however many servers a tenant registers.
 *
 * Bindings accumulate as chips rather than as a checked list, so tools from
 * several servers can be gathered without the picker having to hold every
 * server's catalog at once. A chip is always removable — including one whose
 * server is unreachable or which the server no longer advertises — since
 * `value` alone is authoritative and needs no live option to stay visible.
 *
 * Each chip also carries the input-approval choice for its tool, as a
 * {@link Chip}'s `badge` button sitting before the remove button — a shield
 * icon that toggles between "needs approval" (default) and "skips approval"
 * on click, tinting accent and swapping its icon in the exempt state. Pressed
 * means *exempt*, so a tool just added is bounded by default and nothing has
 * to be kept in two places.
 *
 * The single-select sibling — one `(server, tool)` pair rather than a list — is
 * {@link McpToolField}.
 */
"use client";

import { Server, ShieldCheck, ShieldOff } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { McpServerPickerDialog } from "@/components/admin/mcp-server-picker-dialog";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, type SelectOption } from "@/components/ui/select";
import { useMcpServerTools } from "@/hooks/useMcpServerTools";
import { getApiErrorMessage, listMcpServers } from "@/lib/api";
import { bindingLabel, bindingToValue, valueToBinding } from "@/lib/mcp-tool-options";

/** Upper bound used to read the whole MCP server registry for the name map. */
const SERVER_LIMIT = 1000;

/** DOM id of the tool select, and the prefix of the dialog's panel id. */
const ID_PREFIX = "mcpTool";

/** What the one-off registry read is currently doing. */
type RegistryState =
  | { phase: "loading" }
  | { phase: "ready"; names: Map<string, string> }
  | { phase: "error"; message: string };

/** Props for {@link McpToolPicker}. */
export interface McpToolPickerProps {
  /** Selected composite values (`<serverId>::<toolName>`). */
  value: string[];
  /** Called with the next selection whenever a tool is added or removed. */
  onChange: (next: string[]) => void;
  /**
   * The subset of {@link McpToolPickerProps.value} whose input needs no
   * approval — tools that only read. A tool absent from this list keeps the safe
   * default: an approval covering its task bounds the values it may be called
   * with.
   */
  exempt: string[];
  /** Called with the next exempt subset whenever a chip's badge is toggled. */
  onExemptChange: (next: string[]) => void;
}

/**
 * Controlled multi-select over MCP tools, gathered one server at a time.
 *
 * Reads the server registry once on mount — a plain database listing, with no
 * MCP connection behind it — both to label already-bound tools and to tell "no
 * servers are registered" apart from "the registry could not be read". The
 * chosen server's tools are then fetched on demand by {@link useMcpServerTools},
 * and that fetch's four outcomes (in flight, none advertised, all already added,
 * unreachable) each name themselves in the select rather than all collapsing
 * into an empty dropdown.
 */
export function McpToolPicker({ value, onChange, exempt, onExemptChange }: McpToolPickerProps) {
  const [registry, setRegistry] = useState<RegistryState>({ phase: "loading" });
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(null);
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

  // Stable, so the effect below runs once per input and the retry button can
  // reuse it.
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

  const pickedId = picked?.id ?? null;
  const { state: tools, reload: reloadTools } = useMcpServerTools(pickedId);

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

  const toolNames = tools.phase === "ready" ? tools.tools.map((tool) => tool.name) : [];
  const available = toolNames.filter((name) => !alreadyAdded.has(name));

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
  } else if (toolNames.length === 0) {
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
    // A tool nobody binds has nothing to be exempt from, and leaving it behind
    // would silently re-exempt it if the same tool were bound again later.
    onExemptChange(exempt.filter((v) => v !== composite));
  }

  /** Flip one bound tool's input-approval exemption. */
  function toggleExempt(composite: string) {
    onExemptChange(
      exempt.includes(composite) ? exempt.filter((v) => v !== composite) : [...exempt, composite]
    );
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
                  <Button type="button" variant="secondary" onClick={reloadTools}>
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
            {chips.map((chip) => {
              const isExempt = exempt.includes(chip.value);
              return (
                <Chip
                  key={chip.value}
                  label={chip.label}
                  onRemove={() => removeTool(chip.value)}
                  badge={{
                    icon: isExempt ? ShieldOff : ShieldCheck,
                    active: isExempt,
                    label: isExempt
                      ? "Input needs no approval — click to require approval"
                      : "Input needs approval — click to allow any input",
                    onClick: () => toggleExempt(chip.value),
                  }}
                  size="lg"
                />
              );
            })}
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
