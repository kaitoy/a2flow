/** @module DescriptionDiffDialog — modal showing a word-level diff of a workflow description against its AI-generated original. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { diffWords } from "diff";
import { useMemo } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

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
}: DescriptionDiffDialogProps) {
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useDialogA11y({ open, onClose, panelId: "description-diff-dialog", closeOnOutsideClick: false });

  const parts = useMemo(() => diffWords(generated, description), [generated, description]);
  const changed = parts.some((part) => part.added || part.removed);

  // Guard against SSR — createPortal needs document.body, which is not
  // available during Next.js prerendering.
  if (typeof document === "undefined") return null;

  // An empty description is not an edit of the generated text — it means the
  // workflow session falls back to it verbatim, so a diff would be misleading.
  const emptyDescription = description.trim() === "";

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 bg-black/25 backdrop-blur-[2px] cursor-default"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex items-center justify-center min-h-full p-4 pointer-events-none">
              <animated.div
                id="description-diff-dialog"
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="description-diff-dialog-title"
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className="flex max-h-[80vh] w-full max-w-2xl flex-col glass-panel-overlay rounded-2xl p-6 pointer-events-auto"
              >
                <h2
                  id="description-diff-dialog-title"
                  className="mb-1 font-display text-lg font-semibold tracking-tight text-on-surface"
                >
                  Description diff
                </h2>
                <p className="mb-4 text-sm text-on-surface-variant">
                  Changes the description makes to the generated description.
                </p>
                {emptyDescription ? (
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
                          // Diff parts have no stable identity of their own and
                          // the list is fully recomputed whenever either text
                          // changes, so the index is the only usable key.
                          // biome-ignore lint/suspicious/noArrayIndexKey: diff parts have no stable id
                          <DiffPart key={index} part={part} />
                        ))}
                      </p>
                    </div>
                  </>
                )}
                <div className="mt-4 flex justify-end">
                  <Button variant="ghost" onClick={onClose}>
                    Close
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
