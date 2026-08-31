/**
 * @module useMcpServerTools — Live listing of one MCP server's advertised tools.
 *
 * Shared by {@link import("@/components/admin/mcp-tool-picker").McpToolPicker}
 * (multi-select, on the task-template forms) and
 * {@link import("@/components/admin/mcp-tool-field").McpToolField} (single-select,
 * on the tool-mock form), so the fiddly part — a `stdio` server that can take a
 * minute to answer, a server switched away from while its reply is still in
 * flight, React StrictMode's double mount — is written once.
 *
 * Listing a server's tools makes A2Flow *connect to it live*, so nothing is
 * fetched until a server id is actually passed: a field's own mount cost stays a
 * single registry read, and a server is queried only once it has been picked.
 *
 * The whole {@link McpToolInfo} record is kept, not just the name: the tool-mock
 * form shows the chosen tool's declared output format so the operator can write
 * a mocked response against it.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getApiErrorMessage, listMcpServerTools, type McpToolInfo } from "@/lib/api";

/** What the chosen server's live tool listing is currently doing. */
export type McpServerToolsState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ready"; tools: McpToolInfo[] }
  | { phase: "error"; message: string };

/** Everything a consumer needs to render a server's tool list. */
export interface UseMcpServerToolsResult {
  /** The listing's current phase for the passed `serverId`. */
  state: McpServerToolsState;
  /** Re-run the listing for the current `serverId`; a no-op while it is `null`. */
  reload: () => void;
}

/**
 * Fetch the tools advertised by `serverId`, re-fetching whenever it changes and
 * returning to `idle` when it is `null`.
 *
 * A slow reply that lands after the caller has moved to a different server — or
 * cleared the selection — is dropped rather than shown on top of the current
 * server's tools: each request carries a token, and only the latest token's
 * outcome is applied.
 *
 * @param serverId - The registered MCP server to list, or `null` when none is chosen.
 * @returns The listing state and a manual reload.
 */
export function useMcpServerTools(serverId: string | null): UseMcpServerToolsResult {
  const [state, setState] = useState<McpServerToolsState>({ phase: "idle" });

  // Guards the post-await state updates. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Identifies the in-flight request. A `stdio` server can take a minute to
  // answer, which is long enough for the caller to have picked a different
  // server in the meantime — without this the slow reply would land on top of
  // the new server's tools.
  const requestRef = useRef(0);

  const load = useCallback(async (id: string) => {
    const token = requestRef.current + 1;
    requestRef.current = token;
    setState({ phase: "loading" });
    try {
      const fetched = await listMcpServerTools(id);
      if (!mountedRef.current || requestRef.current !== token) return;
      setState({ phase: "ready", tools: fetched });
    } catch (err) {
      if (!mountedRef.current || requestRef.current !== token) return;
      setState({ phase: "error", message: getApiErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    if (serverId === null) {
      // Abandon whatever is in flight, so a slow reply for the server just
      // cleared cannot repopulate the list after the fact.
      requestRef.current += 1;
      setState({ phase: "idle" });
      return;
    }
    void load(serverId);
  }, [serverId, load]);

  const reload = useCallback(() => {
    if (serverId !== null) void load(serverId);
  }, [serverId, load]);

  return { state, reload };
}
