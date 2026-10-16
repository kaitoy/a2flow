/**
 * @module KnowledgePagesPanel — Browser for the pages of one knowledge base.
 */
"use client";

import { BookOpen } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { MarkdownContentDialog } from "@/components/admin/markdown-content-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { SectionCard } from "@/components/ui/section-card";
import { getKnowledgePage, type KnowledgePageSummary, listKnowledgePages } from "@/lib/api";
import { okfToDisplayMarkdown } from "@/lib/okf-display";

/** Props for {@link KnowledgePagesPanel}. */
export interface KnowledgePagesPanelProps {
  /** The knowledge base whose pages to show. */
  knowledgeBaseId: string;
  /** Changing this re-fetches the list, e.g. after background ingest settled. */
  refreshKey?: number;
}

/**
 * Lists the pages the LLM has written into a knowledge base and opens one as
 * rendered Markdown.
 *
 * Read-only for everyone: the pages are written from the sources, so a wrong
 * page is fixed by fixing or removing its source.
 */
export function KnowledgePagesPanel({ knowledgeBaseId, refreshKey = 0 }: KnowledgePagesPanelProps) {
  const [pages, setPages] = useState<KnowledgePageSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [openPath, setOpenPath] = useState<string | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is the re-fetch trigger
  useEffect(() => {
    let active = true;
    listKnowledgePages(knowledgeBaseId)
      .then((result) => {
        if (active) setPages(result);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [knowledgeBaseId, refreshKey]);

  const loadPage = useCallback(
    async () =>
      openPath
        ? okfToDisplayMarkdown((await getKnowledgePage(knowledgeBaseId, openPath)).content)
        : "",
    [knowledgeBaseId, openPath]
  );

  const columns: ColumnDef<KnowledgePageSummary>[] = [
    {
      header: "Page",
      visibility: "always",
      noTruncate: true,
      cell: (page) => (
        <div className="flex min-w-0 flex-col items-start">
          <button
            type="button"
            onClick={() => setOpenPath(page.path)}
            className="cursor-pointer text-left font-medium text-accent transition-colors hover:underline"
          >
            {page.title}
          </button>
          <span className="font-mono text-xs text-on-surface-variant">{page.path}</span>
          {page.description && (
            <span className="text-xs text-on-surface-variant">{page.description}</span>
          )}
        </div>
      ),
    },
    { header: "Type", cell: (page) => page.type },
    { header: "Updated At", cell: (page) => <DateTime value={page.updatedAt} /> },
  ];

  return (
    <SectionCard icon={BookOpen} title="Pages" className="mt-4">
      <DataTable
        columns={columns}
        rows={pages}
        loading={loading}
        emptyMessage="No pages yet. They appear here once a source has been read."
        emptyIcon={BookOpen}
        getRowKey={(page) => page.path}
      />
      <MarkdownContentDialog
        open={openPath !== null}
        title={pages.find((p) => p.path === openPath)?.title ?? "Page"}
        panelId="knowledge-page-dialog"
        load={loadPage}
        onClose={() => setOpenPath(null)}
      />
    </SectionCard>
  );
}
