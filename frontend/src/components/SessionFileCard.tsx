"use client";

import { Download, FileText } from "lucide-react";
import { sessionFileDownloadUrl } from "@/lib/api";
import { formatFileSize, type SessionFileActivityContent } from "@/lib/sessionFileTool";

/**
 * In-chat card for a file the agent wrote into the session, with a link that
 * downloads it.
 *
 * Rendered from a `write_session_file` tool result, both live and when a
 * reloaded session replays it — which is why the content carries the run id
 * alongside the file id: the card builds its own link and needs nothing from
 * the chat around it.
 *
 * A plain anchor rather than a fetch: the endpoint is cookie-authenticated and
 * already answers with `Content-Disposition: attachment`, so the browser saves
 * the file with no JavaScript in the path.
 */
export function SessionFileCard({ content }: { content: SessionFileActivityContent }) {
  const href = sessionFileDownloadUrl(content.workflowExecutionId, content.fileId);
  return (
    <div className="glass-panel flex items-center gap-3 rounded-2xl p-4 animate-message-in">
      <FileText
        size={20}
        strokeWidth={1.8}
        aria-hidden
        className="shrink-0 text-on-surface-variant"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm font-medium text-on-surface">{content.name}</p>
        <p className="mt-0.5 text-xs text-on-surface-variant">
          {formatFileSize(content.sizeBytes)}
        </p>
      </div>
      <a
        href={href}
        download={content.name}
        aria-label={`Download ${content.name}`}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-on-surface-variant transition-colors duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <Download size={14} strokeWidth={2} aria-hidden />
        Download
      </a>
    </div>
  );
}
