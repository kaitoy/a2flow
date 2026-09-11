/** @module SkillContentDialog — modal rendering an agent skill's SKILL.md as Markdown. */
"use client";

import { renderMarkdown } from "@a2ui/markdown-it";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { getAgentSkillContent } from "@/lib/api";

/** Props for {@link SkillContentDialog}. */
export interface SkillContentDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Identifier of the skill whose SKILL.md to fetch and render. */
  skillId: string;
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
 * Modal dialog rendering the raw SKILL.md file of an agent skill's currently
 * published revision, as Markdown.
 *
 * Fetches on every open rather than caching, since the content only exists
 * once a revision is published and can change on the next pull.
 */
export function SkillContentDialog({ open, skillId, onClose }: SkillContentDialogProps) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setHtml(null);
      return;
    }
    let active = true;
    getAgentSkillContent(skillId)
      .then((result) => renderMarkdown(result.content))
      .then((rendered) => {
        if (active) setHtml(rendered);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      });
    return () => {
      active = false;
    };
  }, [open, skillId]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="skill-content-dialog"
      title="SKILL.md"
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
