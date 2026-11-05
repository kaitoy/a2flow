/** @module PromptDiffDialog — modal showing a word-level diff of a workflow prompt against its AI-generated original. */
"use client";

import { diffWords } from "diff";
import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/provider";

/** Props for {@link PromptDiffDialog}. */
export interface PromptDiffDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Baseline text: the AI-generated prompt the diff is measured from. */
  generated: string;
  /** Compared text: the user-editable prompt that overrides the baseline. */
  prompt: string;
  /** Called when the dialog requests to close (backdrop, Escape, or Close button). */
  onClose: () => void;
  /**
   * Whether the generated prompt is still being summarized server-side.
   * Shows a placeholder skeleton in place of the diff and, matching the
   * streaming chat bubbles, the signature "live edge" around the panel,
   * instead of diffing whatever stale text is still in `generated`.
   */
  loading?: boolean;
}

/** A single word-level change produced by {@link diffWords}. */
interface DiffPartProps {
  part: { value: string; added: boolean; removed: boolean };
}

/**
 * One run of text in the diff body: struck-through and tinted red when it only
 * exists in the generated prompt, tinted green when it only exists in the
 * user's prompt, plain otherwise.
 *
 * Uses `<del>`/`<ins>` so the change survives for assistive tech that ignores
 * colour, and the strike-through gives a second, non-colour cue.
 */
function DiffPart({ part }: DiffPartProps) {
  if (part.removed) {
    return <del className="rounded bg-error/10 px-0.5 text-error line-through">{part.value}</del>;
  }
  if (part.added) {
    return (
      <ins className="rounded bg-success/10 px-0.5 text-success no-underline">{part.value}</ins>
    );
  }
  return <span className="text-on-surface">{part.value}</span>;
}

/**
 * Placeholder shown in place of the legend and diff body while the generated
 * prompt is still being summarized server-side. Mirrors the shape of
 * the real content (a legend-height row, then a multi-line block in a
 * `glass-panel`) so the dialog doesn't jump when the diff swaps in.
 */
function DiffSkeleton() {
  const t = useT();
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={t("admin.generating2")}
      className="flex flex-1 flex-col gap-3"
    >
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-3 w-32" />
      </div>
      <div className="flex flex-1 flex-col gap-2 rounded-xl glass-panel p-4">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}

/** Colour key shown above the diff body. */
function DiffLegend() {
  const t = useT();
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-on-surface-variant text-xs">
      <span className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full bg-error" aria-hidden="true" />
        {t("admin.onlyInTheGeneratedPrompt")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full bg-success" aria-hidden="true" />
        {t("admin.onlyInThePrompt")}
      </span>
    </div>
  );
}

/**
 * Modal dialog rendering a word-level diff from a workflow's generated
 * prompt to its user-editable prompt.
 *
 * The caller passes the values currently held in the edit form, so unsaved
 * edits are diffed too — the point is to see, while writing, what the override
 * changes about the AI's summary.
 */
export function PromptDiffDialog({
  open,
  generated,
  prompt,
  onClose,
  loading = false,
}: PromptDiffDialogProps) {
  const t = useT();
  const parts = useMemo(() => diffWords(generated, prompt), [generated, prompt]);
  const changed = parts.some((part) => part.added || part.removed);

  // An empty prompt is not an edit of the generated text — it means the
  // workflow execution falls back to it verbatim, so a diff would be misleading.
  const emptyPrompt = prompt.trim() === "";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="prompt-diff-dialog"
      title={t("admin.promptDiff")}
      description={t("admin.changesThePromptMakesToTheGenerated")}
      size="lg"
      scrollable
      // Signature "live edge" — matches the streaming chat bubbles — while the
      // server is still summarizing the design conversation into the generated
      // prompt.
      panelClassName={loading ? "live-edge" : undefined}
      footer={
        <Button variant="ghost" onClick={onClose}>
          {t("common.close")}
        </Button>
      }
    >
      {loading ? (
        <DiffSkeleton />
      ) : emptyPrompt ? (
        <p className="text-sm text-on-surface-variant">
          {t("admin.promptIsEmptySoTheGeneratedPrompt")}
        </p>
      ) : !changed ? (
        <p className="text-sm text-on-surface-variant">
          {t("admin.noDifferencesThePromptMatchesTheGenerated")}
        </p>
      ) : (
        <>
          <DiffLegend />
          <div className="flex-1 overflow-y-auto rounded-xl glass-panel p-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {parts.map((part, index) => (
                // Diff parts have no stable identity of their own and the list
                // is fully recomputed whenever either text changes, so the
                // index is the only usable key.
                // biome-ignore lint/suspicious/noArrayIndexKey: diff parts have no stable id
                <DiffPart key={index} part={part} />
              ))}
            </p>
          </div>
        </>
      )}
    </Dialog>
  );
}
