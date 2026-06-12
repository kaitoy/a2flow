/**
 * @module mcp-tool-options — Helpers for picking MCP tool bindings in WorkflowTask forms.
 *
 * Tool bindings are edited through a multi-select whose option values encode a
 * `(server, tool)` pair as a single string, because shared form controls
 * (CheckboxGroup) work on flat string values. These helpers convert between the
 * composite value and the API's {@link ToolBinding} shape, and load the live
 * option catalog from every registered MCP server.
 */

import { listMcpServers, listMcpServerTools, type ToolBinding } from "@/lib/api";

/** Separator between the server id and the tool name inside a composite value. */
const SEPARATOR = "::";

/** Upper bound used to fetch the whole MCP server registry for the picker. */
const SERVER_LIMIT = 1000;

/** One selectable MCP tool: composite value plus a human-readable label. */
export interface McpToolOption {
  value: string;
  label: string;
}

/** Encode a tool binding as a composite option value (`<serverId>::<toolName>`). */
export function bindingToValue(binding: ToolBinding): string {
  return `${binding.mcpServerId}${SEPARATOR}${binding.toolName}`;
}

/** Decode a composite option value back into a tool binding. */
export function valueToBinding(value: string): ToolBinding {
  const index = value.indexOf(SEPARATOR);
  return {
    mcpServerId: value.slice(0, index),
    toolName: value.slice(index + SEPARATOR.length),
  };
}

/** Result of {@link loadMcpToolOptions}. */
export interface McpToolCatalog {
  /** Selectable tools across all reachable registered servers. */
  options: McpToolOption[];
  /** Registered server names by id (includes servers whose tool fetch failed). */
  serverNames: Map<string, string>;
}

/**
 * Load the MCP tool picker catalog: every registered server's advertised tools.
 *
 * Servers that cannot be reached are skipped (their tools simply do not appear)
 * but still contribute their name to {@link McpToolCatalog.serverNames} so
 * already-bound tools can be labeled.
 */
export async function loadMcpToolOptions(): Promise<McpToolCatalog> {
  const servers = await listMcpServers(SERVER_LIMIT, 0);
  const serverNames = new Map(servers.map((s) => [s.id, s.name]));
  const results = await Promise.allSettled(
    servers.map(async (server) => {
      const tools = await listMcpServerTools(server.id);
      return tools.map((tool) => ({
        value: bindingToValue({ mcpServerId: server.id, toolName: tool.name }),
        label: `${server.name}: ${tool.name}`,
      }));
    })
  );
  const options = results
    .filter((r): r is PromiseFulfilledResult<McpToolOption[]> => r.status === "fulfilled")
    .flatMap((r) => r.value);
  return { options, serverNames };
}

/**
 * Ensure every already-bound tool appears in the option list, even when its
 * server is unreachable or no longer advertises the tool, so form prefills stay
 * visible and deselectable.
 */
export function mergeBindingOptions(
  options: McpToolOption[],
  bindings: ToolBinding[],
  serverNames: Map<string, string>
): McpToolOption[] {
  const known = new Set(options.map((o) => o.value));
  const extras = bindings
    .filter((b) => !known.has(bindingToValue(b)))
    .map((b) => ({
      value: bindingToValue(b),
      label: `${serverNames.get(b.mcpServerId) ?? `${b.mcpServerId.slice(0, 8)}…`}: ${b.toolName}`,
    }));
  return [...options, ...extras];
}
