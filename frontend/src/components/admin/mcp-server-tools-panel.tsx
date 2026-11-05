/**
 * @module McpServerToolsPanel — On-demand tool catalog for a registered MCP
 * server's detail page.
 *
 * Fetching a server's tools means A2Flow connects to it live (spawning a
 * subprocess for a `stdio` transport), so this never fetches on mount — only
 * when the operator explicitly clicks "Fetch tools".
 */
"use client";

import { Wrench } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { getApiErrorMessage, listMcpServerTools, type McpToolInfo } from "@/lib/api";

/** Props for {@link McpServerToolsPanel}. */
export interface McpServerToolsPanelProps {
  /** Identifier of the registered MCP server to query on demand. */
  serverId: string;
}

/**
 * Panel showing the tools a registered MCP server advertises, fetched only
 * when the operator clicks "Fetch tools" (never on mount).
 *
 * A fetch failure (e.g. the server is unreachable, or a `${secret:...}`
 * header/env reference cannot be resolved) is shown both as the usual global
 * toast (`fetchEnvelope` in `lib/api.ts`) and inline here, since this panel
 * exists specifically to diagnose whether the server is reachable.
 */
export function McpServerToolsPanel({ serverId }: McpServerToolsPanelProps) {
  const t = useT();
  const fetchAction = useAsyncAction({ showDone: false });
  const [tools, setTools] = useState<McpToolInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFetch() {
    setError(null);
    try {
      await fetchAction.run(async () => {
        setTools(await listMcpServerTools(serverId));
      });
    } catch (err) {
      setTools(null);
      setError(getApiErrorMessage(err));
    }
  }

  return (
    <section
      aria-label={t("common.tools")}
      className="mt-4 flex flex-col gap-4 rounded-2xl glass-panel-strong p-6"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-on-surface">
          <Wrench size={18} strokeWidth={1.8} aria-hidden="true" />
          {t("common.tools")}
        </h2>
        <Button
          variant="secondary"
          onClick={handleFetch}
          disabled={fetchAction.inFlight}
          status={fetchAction.status}
          pendingLabel={t("admin.fetching")}
        >
          {t("admin.fetchTools")}
        </Button>
      </div>

      {fetchAction.inFlight ? (
        <EmptyState icon={Wrench} title={t("admin.fetchingTools")} />
      ) : tools === null ? (
        <>
          <p className="text-sm text-on-surface-variant">
            {t("admin.fetchToSeeTheToolsThisServer")}
          </p>
          {error && <p className="text-xs text-error">{error}</p>}
        </>
      ) : tools.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title={t("admin.noToolsAdvertised")}
          description={t("admin.thisServerDidNotReportAnyTools")}
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {tools.map((tool) => (
            <li key={tool.name} className="rounded-xl glass-panel p-3">
              <p className="font-mono text-sm font-medium text-on-surface">{tool.name}</p>
              {tool.description && (
                <p className="mt-0.5 line-clamp-2 text-sm text-on-surface-variant">
                  {tool.description}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
