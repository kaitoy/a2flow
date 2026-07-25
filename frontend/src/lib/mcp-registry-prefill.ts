/**
 * @module mcp-registry-prefill — encode/decode the create-form prefill carried in
 * the URL when a server is chosen from the MCP registry search dialog.
 *
 * The registry search dialog navigates to the "New MCP Server" form with the
 * chosen server's name and transport-specific connection details encoded as
 * query params; the form decodes them to seed its default values so the
 * operator only has to fill in secret header/environment values before saving.
 */
import type { McpCommand, McpRegistryServerEntry, McpTransport } from "@/lib/api";

/** One editable key/value row carried through the prefill. */
interface PrefillPair {
  key: string;
  value: string;
}

/** Decoded prefill values for the "New MCP Server" create form. */
export interface McpServerPrefill {
  /** Suggested server name. */
  name: string;
  /** Transport the entry is registrable through. */
  transport: McpTransport;
  /** Streamable-HTTP endpoint URL; empty for a stdio entry. */
  url: string;
  /** Header key/value pairs (secret values come through empty for the operator). */
  headers: PrefillPair[];
  /** Executable launching a stdio server; `"npx"` for a remote entry. */
  command: McpCommand;
  /** `argv` entries for a stdio server, in order. */
  args: string[];
  /** Environment key/value pairs (secret values come through empty for the operator). */
  env: PrefillPair[];
}

/** Route of the create form the prefill targets. */
const NEW_SERVER_PATH = "/admin/mcp-servers/new";

/**
 * Build the create-form href that pre-fills the connection details from a
 * registry server entry.
 *
 * @param entry - The chosen registry server.
 * @returns A relative href to the create form with prefill query params.
 */
export function buildPrefillHref(entry: McpRegistryServerEntry): string {
  const params = new URLSearchParams();
  params.set("name", entry.title || entry.name);
  params.set("transport", entry.transport ?? "streamable_http");

  if (entry.transport === "stdio") {
    params.set("command", entry.command ?? "");
    if (entry.args && entry.args.length > 0) params.set("args", JSON.stringify(entry.args));
    const env = (entry.env ?? []).map((variable) => ({
      key: variable.name,
      value: variable.value ?? "",
    }));
    if (env.length > 0) params.set("env", JSON.stringify(env));
  } else {
    params.set("url", entry.url ?? "");
    const headers = (entry.headers ?? []).map((header) => ({
      key: header.name,
      value: header.value ?? "",
    }));
    if (headers.length > 0) params.set("headers", JSON.stringify(headers));
  }

  return `${NEW_SERVER_PATH}?${params.toString()}`;
}

/**
 * Parse a JSON-encoded query param into a list, dropping anything that does not
 * match `isItem`.
 *
 * @param raw - The raw query param value, or `null` when absent.
 * @param isItem - Type guard applied to each decoded element.
 * @returns The surviving elements; an empty list when absent or malformed.
 */
function parseJsonList<T>(raw: string | null, isItem: (item: unknown) => item is T): T[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isItem) : [];
  } catch {
    return [];
  }
}

/** Type guard for a decoded key/value prefill row. */
function isPrefillPair(item: unknown): item is PrefillPair {
  return (
    typeof item === "object" &&
    item !== null &&
    typeof (item as { key?: unknown }).key === "string" &&
    typeof (item as { value?: unknown }).value === "string"
  );
}

/** Type guard for a decoded `argv` entry. */
function isArg(item: unknown): item is string {
  return typeof item === "string";
}

/**
 * Decode prefill values from the create form's URL search params.
 *
 * Accepts anything with a `get(name)` accessor so Next.js'
 * `ReadonlyURLSearchParams` (from `useSearchParams`) can be passed directly.
 *
 * @param params - The form route's search params.
 * @returns Prefill values; empty strings / empty lists when absent or
 *   malformed, `streamable_http` for an absent or unrecognized transport, and
 *   `"npx"` for an absent or unrecognized command.
 */
export function parsePrefill(params: Pick<URLSearchParams, "get">): McpServerPrefill {
  const transport: McpTransport = params.get("transport") === "stdio" ? "stdio" : "streamable_http";

  return {
    name: params.get("name") ?? "",
    transport,
    url: params.get("url") ?? "",
    headers: parseJsonList(params.get("headers"), isPrefillPair),
    command: params.get("command") === "uvx" ? "uvx" : "npx",
    args: parseJsonList(params.get("args"), isArg),
    env: parseJsonList(params.get("env"), isPrefillPair),
  };
}
