/** @module DescriptionDiffDialog — modal showing a word-level diff of a workflow description against its AI-generated original. */
"use client";

import { diffWords } from "diff";
import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

/** Props for {@link DescriptionDiffDialog}. */
export interface DescriptionDiffDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Baseline text: the AI-generated description the diff is measured from. */
  generated: string;
  /** Compared text: the user-editable description that overrides the baseline. */
  description: string;
  /** Called when the dialog requests to close (backdrop, Escape, or Close button). */
  onClose: () => void;
  /**
   * Whether the generated description is still being summarized server-side.
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
 * exists in the generated description, tinted green when it only exists in the
 * user's description, plain otherwise.
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
 * description is still being summarized server-side. Mirrors the shape of
 * the real content (a legend-height row, then a multi-line block in a
 * `glass-panel`) so the dialog doesn't jump when the diff swaps in.
 */
function DiffSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Generating"
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
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-on-surface-variant text-xs">
      <span className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full bg-error" aria-hidden="true" />
        Only in the generated description
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block size-2 rounded-full bg-success" aria-hidden="true" />
        Only in the description
      </span>
    </div>
  );
}

/**
 * Modal dialog rendering a word-level diff from a workflow's generated
 * description to its user-editable description.
 *
 * The caller passes the values currently held in the edit form, so unsaved
 * edits are diffed too — the point is to see, while writing, what the override
 * changes about the AI's summary.
 */
export function DescriptionDiffDialog({
  open,
  generated,
  description,
  onClose,
  loading = false,
}: DescriptionDiffDialogProps) {
  const parts = useMemo(() => diffWords(generated, description), [generated, description]);
  const changed = parts.some((part) => part.added || part.removed);

  // An empty description is not an edit of the generated text — it means the
  // workflow execution falls back to it verbatim, so a diff would be misleading.
  const emptyDescription = description.trim() === "";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="description-diff-dialog"
      title="Description diff"
      description="Changes the description makes to the generated description."
      size="lg"
      scrollable
      // Signature "live edge" — matches the streaming chat bubbles — while the
      // server is still summarizing the design conversation into the generated
      // description.
      panelClassName={loading ? "live-edge" : undefined}
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      {loading ? (
        <DiffSkeleton />
      ) : emptyDescription ? (
        <p className="text-sm text-on-surface-variant">
          Description is empty, so the generated description is used as is.
        </p>
      ) : !changed ? (
        <p className="text-sm text-on-surface-variant">
          No differences — the description matches the generated description.
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
