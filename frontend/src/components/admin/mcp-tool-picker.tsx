/**
 * @module McpToolPicker — Multi-select for binding MCP tools to a workflow task.
 *
 * Shared by the create and edit task-template forms so the two stay in step,
 * mirroring how {@link McpServerFields} is shared between the MCP server forms.
 *
 * Building the option list means A2Flow connects to every registered MCP server
 * live, and a `stdio` server spawns a subprocess that can take a minute to come
 * up. Unlike {@link McpServerToolsPanel} the fetch still happens on mount — a
 * picker with no options is useless — so this component's job is to make the
 * wait and any per-server failure legible instead of rendering an empty list
 * that reads as "no MCP servers are registered".
 */
"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage, type ToolBinding } from "@/lib/api";
import {
  loadMcpToolOptions,
  type McpToolCatalog,
  type McpToolOption,
  mergeBindingOptions,
} from "@/lib/mcp-tool-options";

/** Option count above which a filter box is worth showing. */
const FILTER_THRESHOLD = 12;

/** Stable identity for the default `boundBindings`, so memos don't rerun needlessly. */
const NO_BINDINGS: ToolBinding[] = [];

/** What the catalog fetch is currently doing. */
type LoadState =
  | { phase: "loading" }
  | { phase: "ready"; catalog: McpToolCatalog }
  | { phase: "error"; message: string };

/** Props for {@link McpToolPicker}. */
export interface McpToolPickerProps {
  /** Selected composite values (`<serverId>::<toolName>`). */
  value: string[];
  /** Called with the next selection whenever a tool is toggled. */
  onChange: (next: string[]) => void;
  /**
   * Bindings already stored on the task. They stay selectable even when their
   * server is unreachable or no longer advertises the tool, so an existing
   * binding can always be removed.
   */
  boundBindings?: ToolBinding[];
}

/**
 * Group options by server and mark the first option of each group with a
 * divider, so a long flat list reads as one block per MCP server.
 */
function groupByServer(options: McpToolOption[]): CheckboxOption[] {
  const byServer = new Map<string, McpToolOption[]>();
  for (const option of options) {
    const group = byServer.get(option.serverId);
    if (group) group.push(option);
    else byServer.set(option.serverId, [option]);
  }
  return [...byServer.values()].flatMap((group, groupIndex) =>
    group.map((option, index) => ({
      value: option.value,
      label: option.label,
      dividerBefore: groupIndex > 0 && index === 0,
    }))
  );
}

/**
 * Controlled multi-select over the tools advertised by every registered MCP
 * server, loaded on mount.
 *
 * Distinguishes the four states an empty list can mean — still loading, no
 * servers registered at all, the registry itself failed, and some servers
 * unreachable — and offers a retry for the last two. Above
 * {@link FILTER_THRESHOLD} options a filter box appears; already-selected tools
 * are always kept in the rendered list, both so the current selection stays
 * visible and because {@link CheckboxGroup} derives the next selection from the
 * options it was given.
 */
export function McpToolPicker({
  value,
  onChange,
  boundBindings = NO_BINDINGS,
}: McpToolPickerProps) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [query, setQuery] = useState("");

  // Guards the post-await state updates. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Stable, so the effect below runs once and the retry button can reuse it.
  const load = useCallback(async () => {
    setState({ phase: "loading" });
    try {
      const catalog = await loadMcpToolOptions();
      if (mountedRef.current) setState({ phase: "ready", catalog });
    } catch (err) {
      if (mountedRef.current) setState({ phase: "error", message: getApiErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const catalog = state.phase === "ready" ? state.catalog : null;

  const allOptions = useMemo(
    () =>
      catalog
        ? mergeBindingOptions(catalog.options, boundBindings, catalog.serverNames)
        : mergeBindingOptions([], boundBindings, new Map()),
    [catalog, boundBindings]
  );

  const visibleOptions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matching = needle
      ? allOptions.filter((o) => o.label.toLowerCase().includes(needle) || value.includes(o.value))
      : allOptions;
    return groupByServer(matching);
  }, [allOptions, query, value]);

  if (state.phase === "loading") {
    return (
      <div className="rounded-xl glass-panel px-4 py-3">
        <EmptyState
          icon={Wrench}
          compact
          title="Loading tools…"
          description="Connecting to the registered MCP servers."
        />
      </div>
    );
  }

  if (state.phase === "error") {
    return (
      <div className="flex flex-col items-start gap-2 rounded-xl glass-panel px-4 py-3">
        <p className="text-sm text-on-surface-variant">Could not load the MCP server registry.</p>
        <p className="text-xs text-error">{state.message}</p>
        <Button type="button" variant="secondary" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }

  const noServersRegistered = state.catalog.serverNames.size === 0;
  const { failures } = state.catalog;

  return (
    <div className="flex flex-col gap-2">
      {noServersRegistered ? (
        <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
          No MCP servers are registered.{" "}
          <Link href="/admin/mcp-servers" className="text-accent transition-colors hover:underline">
            Register one
          </Link>{" "}
          to bind its tools to this task.
        </p>
      ) : (
        <>
          {allOptions.length > FILTER_THRESHOLD && (
            <Input
              aria-label="Filter tools"
              placeholder="Filter tools…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          <CheckboxGroup
            name="toolBindings"
            options={visibleOptions}
            value={value}
            onChange={onChange}
            emptyMessage={
              query.trim()
                ? "No tools match the filter."
                : "The registered MCP servers advertise no tools."
            }
          />
        </>
      )}

      {failures.length > 0 && (
        <div className="flex flex-col items-start gap-1.5 rounded-xl glass-panel px-4 py-3">
          <p className="text-xs text-on-surface-variant">
            {failures.length === 1
              ? "1 registered server could not be queried, so its tools are missing:"
              : `${failures.length} registered servers could not be queried, so their tools are missing:`}
          </p>
          <ul className="flex flex-col gap-0.5">
            {failures.map((failure) => (
              <li key={failure.serverId} className="text-xs text-error">
                <span className="font-medium">{failure.serverName}</span>: {failure.message}
              </li>
            ))}
          </ul>
          <Button type="button" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
