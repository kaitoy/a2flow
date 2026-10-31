/** @module MarkdownContentDialog — modal fetching a Markdown document and rendering it. */
"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { renderMarkdown } from "@/lib/markdown";

/** Props for {@link MarkdownContentDialog}. */
export interface MarkdownContentDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Dialog heading. */
  title: string;
  /** DOM id of the dialog panel; must be unique on the page. */
  panelId: string;
  /**
   * Fetches the Markdown to render. Called on every open; must be stable
   * (wrap it in `useCallback`) or the dialog refetches on each render.
   */
  load: () => Promise<string>;
  /** Called when the dialog requests to close (backdrop, Escape, or Close button). */
  onClose: () => void;
}

/** Placeholder shown while the content is being fetched and rendered. */
function ContentSkeleton() {
  return (
    <div className="flex flex-1 flex-col gap-2 rounded-xl glass-panel p-4">
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

/**
 * Modal dialog rendering a Markdown document fetched when it opens — a skill's
 * SKILL.md, a knowledge base page.
 *
 * Fetches on every open rather than caching, since what it shows is server
 * state that can change between opens.
 */
export function MarkdownContentDialog({
  open,
  title,
  panelId,
  load,
  onClose,
}: MarkdownContentDialogProps) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setHtml(null);
      return;
    }
    let active = true;
    load()
      .then((markdown) => renderMarkdown(markdown))
      .then((rendered) => {
        if (active) setHtml(rendered);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      });
    return () => {
      active = false;
    };
  }, [open, load]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId={panelId}
      title={title}
      size="lg"
      scrollable
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      {html === null ? (
        <ContentSkeleton />
      ) : (
        <div
          className="markdown-body flex-1 overflow-y-auto rounded-xl glass-panel p-4"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: sanitized via @a2ui/markdown-it (DOMPurify) before render
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </Dialog>
  );
}
