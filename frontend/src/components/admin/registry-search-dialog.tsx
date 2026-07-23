/** @module RegistrySearchDialog — modal to search the official MCP registry. */
import { animated, useTransition } from "@react-spring/web";
import { PackageSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { type McpRegistryServerEntry, searchMcpRegistry } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";

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
 * operator pick a streamable-HTTP server to pre-fill the create form.
 *
 * Only servers A2Flow can register (those exposing a streamable-HTTP remote)
 * are returned by the backend, so every result is selectable.
 */
export function RegistrySearchDialog({ open, onClose, onSelect }: RegistrySearchDialogProps) {
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

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

  useDialogA11y({ open, onClose, panelId: "registry-search-dialog", closeOnOutsideClick: false });

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

  // Guard against SSR — createPortal needs document.body.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 h-full w-full cursor-default border-0 bg-black/25 backdrop-blur-[2px]"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              aria-label="Close registry search"
              tabIndex={-1}
            />
            <div className="relative flex min-h-full items-center justify-center p-4 pointer-events-none">
              <animated.div
                id="registry-search-dialog"
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="registry-search-title"
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-2xl glass-panel-overlay p-6 pointer-events-auto"
              >
                <h2
                  id="registry-search-title"
                  className="mb-1 font-display text-lg font-semibold tracking-tight text-on-surface"
                >
                  Browse MCP Registry
                </h2>
                <p className="mb-4 text-sm text-on-surface-variant">
                  Search the official MCP registry by name. Only servers reachable over streamable
                  HTTP are shown.
                </p>

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
                        loading
                          ? undefined
                          : "Try a different name, or check back as the registry grows."
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
                            <p className="truncate font-medium text-on-surface">
                              {server.title || server.name}
                              <span className="ml-2 font-mono text-xs text-on-surface-variant">
                                v{server.version}
                              </span>
                            </p>
                            {server.description && (
                              <p className="mt-0.5 line-clamp-2 text-sm text-on-surface-variant">
                                {server.description}
                              </p>
                            )}
                            <p className="mt-0.5 truncate font-mono text-xs text-on-surface-variant">
                              {server.url}
                            </p>
                          </div>
                          <Button
                            variant="primary"
                            className="shrink-0"
                            onClick={() => onSelect(server)}
                          >
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

                <div className="mt-4 flex justify-end">
                  <Button variant="ghost" onClick={onClose}>
                    Cancel
                  </Button>
                </div>
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
