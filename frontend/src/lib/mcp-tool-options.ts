/**
 * @module mcp-tool-options — Helpers for picking MCP tool bindings in WorkflowTask forms.
 *
 * Tool bindings are edited through a multi-select whose option values encode a
 * `(server, tool)` pair as a single string, because shared form controls
 * (CheckboxGroup) work on flat string values. These helpers convert between the
 * composite value and the API's {@link ToolBinding} shape, and load the live
 * option catalog from every registered MCP server.
 */

import {
  getApiErrorMessage,
  listMcpServers,
  listMcpServerTools,
  type ToolBinding,
} from "@/lib/api";

/** Separator between the server id and the tool name inside a composite value. */
const SEPARATOR = "::";

/** Upper bound used to fetch the whole MCP server registry for the picker. */
const SERVER_LIMIT = 1000;

/** One selectable MCP tool: composite value plus a human-readable label. */
export interface McpToolOption {
  value: string;
  label: string;
  /** Id of the server advertising this tool, so options can be grouped by server. */
  serverId: string;
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

/** One registered server whose tool listing could not be fetched. */
export interface McpToolLoadFailure {
  serverId: string;
  serverName: string;
  /** Human-readable reason, as returned by the API. */
  message: string;
}

/** Result of {@link loadMcpToolOptions}. */
export interface McpToolCatalog {
  /** Selectable tools across all reachable registered servers. */
  options: McpToolOption[];
  /** Registered server names by id (includes servers whose tool fetch failed). */
  serverNames: Map<string, string>;
  /**
   * Servers that are registered but could not be queried. Surfaced so the
   * picker can say *why* a server's tools are missing instead of rendering an
   * empty list that looks like "no MCP servers are registered".
   */
  failures: McpToolLoadFailure[];
}

/**
 * Load the MCP tool picker catalog: every registered server's advertised tools.
 *
 * Each server is queried live and independently, so one unreachable server
 * never hides the others' tools. Servers that fail are reported in
 * {@link McpToolCatalog.failures} — and still contribute their name to
 * {@link McpToolCatalog.serverNames} so already-bound tools can be labeled.
 *
 * A failure to list the registry itself is not caught here: it means the whole
 * catalog is unknown rather than partially known, so it propagates to the
 * caller.
 */
export async function loadMcpToolOptions(): Promise<McpToolCatalog> {
  const servers = await listMcpServers({ limit: SERVER_LIMIT });
  const serverNames = new Map(servers.map((s) => [s.id, s.name]));
  const results = await Promise.allSettled(
    servers.map(async (server) => {
      const tools = await listMcpServerTools(server.id);
      return tools.map((tool) => ({
        value: bindingToValue({ mcpServerId: server.id, toolName: tool.name }),
        label: `${server.name}: ${tool.name}`,
        serverId: server.id,
      }));
    })
  );

  const options: McpToolOption[] = [];
  const failures: McpToolLoadFailure[] = [];
  results.forEach((result, index) => {
    const server = servers[index];
    if (result.status === "fulfilled") {
      options.push(...result.value);
    } else {
      failures.push({
        serverId: server.id,
        serverName: server.name,
        message: getApiErrorMessage(result.reason),
      });
    }
  });
  return { options, serverNames, failures };
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
      serverId: b.mcpServerId,
    }));
  return [...options, ...extras];
}
