/**
 * @module KnowledgeSourcesPanel — The URLs and documents feeding one knowledge
 * base, with their ingest state.
 */
"use client";

import { FileText, RefreshCw, Upload } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { Input } from "@/components/ui/input";
import { SectionCard } from "@/components/ui/section-card";
import { StatusDot } from "@/components/ui/status-dot";
import { useT } from "@/i18n/provider";
import {
  addKnowledgeFileSource,
  addKnowledgeUrlSource,
  deleteKnowledgeSource,
  type KnowledgeSource,
  listKnowledgeSources,
  reingestKnowledgeSource,
} from "@/lib/api";
import {
  formatKnowledgeSourceStatus,
  isKnowledgeSourceBusy,
  isKnowledgeSourceLlmActive,
  KNOWLEDGE_SOURCE_STATUS_DOT_CLASS,
} from "@/lib/knowledge-source-status";

/** How often the panel re-fetches while a source is still being processed. */
const POLL_INTERVAL_MS = 3000;

/** File types the server reads, offered by the file picker. */
const ACCEPTED_FILES = ".pdf,.docx,.txt,.md,.markdown,.html,.htm,.csv,.json";

/** Props for {@link KnowledgeSourcesPanel}. */
export interface KnowledgeSourcesPanelProps {
  /** The knowledge base whose sources to show. */
  knowledgeBaseId: string;
  /** Whether the viewer may add, re-read, and remove sources. */
  canEdit: boolean;
  /**
   * Called when background processing finishes (no source is queued, being
   * read, or being removed any more), so the page can refresh the pages the
   * work changed.
   */
  onSettled?: () => void;
}

/** What a source is: its link or file name, and its title once read. */
function SourceCell({ source }: { source: KnowledgeSource }) {
  const label = source.url ?? source.fileName ?? source.id;
  return (
    <div className="flex min-w-0 flex-col">
      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noreferrer noopener"
          className="truncate font-medium text-accent hover:underline"
        >
          {label}
        </a>
      ) : (
        <span className="truncate font-medium text-on-surface">{label}</span>
      )}
      {source.title && (
        <span className="truncate text-xs text-on-surface-variant">{source.title}</span>
      )}
    </div>
  );
}

/**
 * Lists a knowledge base's sources and lets a developer add web pages, upload
 * documents, re-read a source, or remove one.
 *
 * Reading and removing happen in the background on the server, so every action
 * answers at once with the source queued; the panel then polls until nothing
 * is in flight. While the LLM agent is reading or removing a source, the card
 * plays the "live-edge" light, like every other view where an LLM is at work.
 */
export function KnowledgeSourcesPanel({
  knowledgeBaseId,
  canEdit,
  onSettled,
}: KnowledgeSourcesPanelProps) {
  const t = useT();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<KnowledgeSource | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wasBusy = useRef(false);

  const load = useCallback(async () => {
    try {
      setSources(await listKnowledgeSources(knowledgeBaseId));
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const busy = sources.some((s) => isKnowledgeSourceBusy(s.status));
  const live = sources.some((s) => isKnowledgeSourceLlmActive(s.status));

  useEffect(() => {
    if (wasBusy.current && !busy) onSettled?.();
    wasBusy.current = busy;
    if (!busy) return;
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [busy, load, onSettled]);

  async function handleAddUrl(event: FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    setAdding(true);
    try {
      await addKnowledgeUrlSource(knowledgeBaseId, url.trim());
      setUrl("");
      await load();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setAdding(false);
    }
  }

  async function handleFiles(files: File[]) {
    if (files.length === 0) return;
    setUploading(true);
    try {
      for (const file of files) {
        await addKnowledgeFileSource(knowledgeBaseId, file);
      }
    } catch {
      // Failure toast is shown globally by api.ts; the files before it are in.
    } finally {
      setUploading(false);
      await load();
    }
  }

  async function act(call: () => Promise<unknown>) {
    try {
      await call();
      await load();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const columns: ColumnDef<KnowledgeSource>[] = [
    {
      header: "admin.source",
      visibility: "always",
      noTruncate: true,
      cell: (source) => <SourceCell source={source} />,
    },
    {
      header: "common.status",
      noTruncate: true,
      cell: (source) => (
        <div className="flex flex-col gap-0.5">
          <StatusDot
            dotClass={KNOWLEDGE_SOURCE_STATUS_DOT_CLASS[source.status]}
            label={formatKnowledgeSourceStatus(source.status)}
          />
          {source.status === "failed" && source.error && (
            <span className="text-xs text-error">{source.error}</span>
          )}
        </div>
      ),
    },
    {
      header: "admin.readAt",
      cell: (source) => (source.ingestedAt ? <DateTime value={source.ingestedAt} /> : "—"),
    },
    ...(canEdit
      ? [
          {
            header: "common.actions" as const,
            noTruncate: true,
            visibility: "always" as const,
            cell: (source: KnowledgeSource) => (
              <div className="flex justify-center gap-2">
                <ActionIconButton
                  icon={RefreshCw}
                  label={
                    source.status === "unread" ? t("knowledge.readSource") : t("admin.readAgain")
                  }
                  onClick={() =>
                    void act(() => reingestKnowledgeSource(knowledgeBaseId, source.id))
                  }
                  disabled={source.status === "removing"}
                  spinning={source.status === "pending" || source.status === "ingesting"}
                />
                <DeleteIconButton
                  onClick={() => setRemoveTarget(source)}
                  disabled={source.status === "removing"}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <SectionCard
      icon={FileText}
      title={t("admin.sources")}
      className={live ? "mt-4 live-edge" : "mt-4"}
    >
      {canEdit && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <form onSubmit={handleAddUrl} className="flex min-w-0 flex-1 gap-2">
            <Input
              aria-label={t("admin.webPageUrl")}
              placeholder="https://example.com/handbook"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Button
              type="submit"
              variant="primary"
              disabled={adding || !url.trim()}
              className="shrink-0 whitespace-nowrap"
            >
              {t("admin.addUrl")}
            </Button>
          </form>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            accept={ACCEPTED_FILES}
            onChange={(e) => {
              void handleFiles(Array.from(e.target.files ?? []));
              // Clear the input so picking the same file twice re-fires change.
              e.target.value = "";
            }}
          />
          <Button
            type="button"
            variant="ghost"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={16} aria-hidden="true" />
            {uploading ? t("common.uploading") : t("admin.uploadDocuments")}
          </Button>
        </div>
      )}
      <DataTable
        columns={columns}
        rows={sources}
        loading={loading}
        emptyMessage={t("admin.noSourcesYetAddAWebPage")}
        emptyIcon={FileText}
        getRowKey={(source) => source.id}
      />
      <ConfirmDialog
        open={removeTarget !== null}
        title={t("admin.removeSource")}
        confirmLabel={t("common.remove")}
        description={t("admin.removeThisSourceWhatTheWikiLearned")}
        onConfirm={() => {
          const target = removeTarget;
          setRemoveTarget(null);
          if (target) void act(() => deleteKnowledgeSource(knowledgeBaseId, target.id));
        }}
        onCancel={() => setRemoveTarget(null)}
      />
    </SectionCard>
  );
}
