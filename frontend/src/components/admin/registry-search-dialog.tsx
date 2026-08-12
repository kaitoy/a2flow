/** @module RegistrySearchDialog — modal to search the official MCP registry. */
import { PackageSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { type McpRegistryServerEntry, searchMcpRegistry } from "@/lib/api";

/** Props for {@link RegistrySearchDialog}. */
export interface RegistrySearchDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog requests to close (backdrop, Escape, or Cancel). */
  onClose: () => void;
  /** Called with the chosen server when the operator picks a result. */
  onSelect: (entry: McpRegistryServerEntry) => void;
}

/** Debounce, in milliseconds, applied to the search term before querying. */
const DEBOUNCE_MS = 300;

/**
 * Modal dialog that searches the official MCP registry by name and lets the
 * operator pick a server to pre-fill the create form.
 *
 * Only servers A2Flow can register are returned by the backend — those exposing
 * a streamable-HTTP remote, or publishing an npm/PyPI stdio package — so every
 * result is selectable.
 */
export function RegistrySearchDialog({ open, onClose, onSelect }: RegistrySearchDialogProps) {
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [servers, setServers] = useState<McpRegistryServerEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const loadMoreAction = useAsyncAction({ showDone: false });

  // Reset all state when the dialog closes so it reopens clean.
  useEffect(() => {
    if (open) return;
    setTerm("");
    setQuery("");
    setServers([]);
    setCursor(null);
  }, [open]);

  // Debounce the typed term into the committed query.
  useEffect(() => {
    const id = setTimeout(() => setQuery(term.trim()), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [term]);

  // Fetch the first page whenever the dialog opens or the query changes.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    searchMcpRegistry({ search: query || undefined })
      .then((result) => {
        if (cancelled) return;
        setServers(result.servers);
        setCursor(result.nextCursor ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        // Failure toast is shown globally by api.ts; still clear stale results.
        setServers([]);
        setCursor(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, query]);

  async function loadMore() {
    if (!cursor) return;
    try {
      await loadMoreAction.run(async () => {
        const result = await searchMcpRegistry({ search: query || undefined, cursor });
        setServers((prev) => [...prev, ...result.servers]);
        setCursor(result.nextCursor ?? null);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="registry-search-dialog"
      title="Browse MCP Registry"
      description="Search the official MCP registry by name. Only servers A2Flow can register are shown: those reachable over streamable HTTP, and those published as an npm or PyPI package it can launch over stdio."
      size="lg"
      scrollable
      footer={
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      }
    >
      <Input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="e.g. github, weather, search…"
        aria-label="Search the MCP registry"
      />

      <div className="mt-4 flex-1 overflow-y-auto">
        {servers.length === 0 ? (
          <EmptyState
            icon={PackageSearch}
            title={loading ? "Searching…" : "No servers found"}
            description={
              loading ? undefined : "Try a different name, or check back as the registry grows."
            }
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {servers.map((server) => (
              <li
                key={`${server.name}@${server.version}`}
                className="flex items-start justify-between gap-3 rounded-xl glass-panel p-3"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate font-medium text-on-surface">
                    {server.title || server.name}
                    <span className="font-mono text-xs text-on-surface-variant">
                      v{server.version}
                    </span>
                    <Badge>{server.transport === "stdio" ? "stdio" : "HTTP"}</Badge>
                  </p>
                  {server.description && (
                    <p className="mt-0.5 line-clamp-2 text-sm text-on-surface-variant">
                      {server.description}
                    </p>
                  )}
                  <p className="mt-0.5 truncate font-mono text-xs text-on-surface-variant">
                    {server.transport === "stdio"
                      ? [server.command, ...(server.args ?? [])].join(" ")
                      : server.url}
                  </p>
                </div>
                <Button variant="primary" className="shrink-0" onClick={() => onSelect(server)}>
                  Use this
                </Button>
              </li>
            ))}
          </ul>
        )}

        {cursor && (
          <div className="mt-3 flex justify-center">
            <Button
              variant="secondary"
              onClick={loadMore}
              disabled={loadMoreAction.inFlight}
              status={loadMoreAction.status}
              pendingLabel="Loading…"
            >
              Load more
            </Button>
          </div>
        )}
      </div>
    </Dialog>
  );
}
