/** @module SkillContentDialog — modal rendering an agent skill's SKILL.md as Markdown. */
"use client";

import { useCallback } from "react";
import { MarkdownContentDialog } from "@/components/admin/markdown-content-dialog";
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

/**
 * Modal dialog rendering the raw SKILL.md file of an agent skill's currently
 * published revision, as Markdown.
 *
 * Fetches on every open rather than caching, since the content only exists
 * once a revision is published and can change on the next pull.
 */
export function SkillContentDialog({ open, skillId, onClose }: SkillContentDialogProps) {
  const load = useCallback(async () => (await getAgentSkillContent(skillId)).content, [skillId]);
  return (
    <MarkdownContentDialog
      open={open}
      title="SKILL.md"
      panelId="skill-content-dialog"
      load={load}
      onClose={onClose}
    />
  );
}
