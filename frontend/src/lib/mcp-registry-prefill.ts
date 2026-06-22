/**
 * @module mcp-registry-prefill — encode/decode the create-form prefill carried in
 * the URL when a server is chosen from the MCP registry search dialog.
 *
 * The registry search dialog navigates to the "New MCP Server" form with the
 * chosen server's name, URL, and header keys encoded as query params; the form
 * decodes them to seed its default values so the operator only has to fill in
 * secret header values before saving.
 */
import type { McpRegistryServerEntry } from "@/lib/api";

/** Decoded prefill values for the "New MCP Server" create form. */
export interface McpServerPrefill {
  /** Suggested server name. */
  name: string;
  /** Streamable-HTTP endpoint URL. */
  url: string;
  /** Header key/value pairs (secret values come through empty for the operator). */
  headers: { key: string; value: string }[];
}

/** Route of the create form the prefill targets. */
const NEW_SERVER_PATH = "/admin/mcp-servers/new";

/**
 * Build the create-form href that pre-fills name, URL, and header keys from a
 * registry server entry.
 *
 * @param entry - The chosen registry server.
 * @returns A relative href to the create form with prefill query params.
 */
export function buildPrefillHref(entry: McpRegistryServerEntry): string {
  const headers = (entry.headers ?? []).map((header) => ({
    key: header.name,
    value: header.value ?? "",
  }));
  const params = new URLSearchParams();
  params.set("name", entry.title || entry.name);
  params.set("url", entry.url);
  if (headers.length > 0) params.set("headers", JSON.stringify(headers));
  return `${NEW_SERVER_PATH}?${params.toString()}`;
}

/**
 * Decode prefill values from the create form's URL search params.
 *
 * Accepts anything with a `get(name)` accessor so Next.js'
 * `ReadonlyURLSearchParams` (from `useSearchParams`) can be passed directly.
 *
 * @param params - The form route's search params.
 * @returns Prefill values; empty strings / an empty header list when absent or
 *   malformed.
 */
export function parsePrefill(params: Pick<URLSearchParams, "get">): McpServerPrefill {
  const name = params.get("name") ?? "";
  const url = params.get("url") ?? "";

  let headers: { key: string; value: string }[] = [];
  const raw = params.get("headers");
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        headers = parsed
          .filter(
            (item): item is { key: string; value: string } =>
              typeof item === "object" &&
              item !== null &&
              typeof (item as { key?: unknown }).key === "string" &&
              typeof (item as { value?: unknown }).value === "string"
          )
          .map((item) => ({ key: item.key, value: item.value }));
      }
    } catch {
      headers = [];
    }
  }

  return { name, url, headers };
}
