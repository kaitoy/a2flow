/**
 * @module ChipRow — single-line row of {@link Chip}s that folds whatever does not
 * fit into one trailing `+N` chip. Clicking that chip opens a dialog listing
 * every chip in the row, each with its own description tooltip.
 */
"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { TagColor } from "@/lib/api";
import { Button } from "./button";
import { Chip } from "./chip";
import { Dialog } from "./dialog";

/** One chip in a {@link ChipRow}. */
export interface ChipRowItem {
  /** Stable React key, e.g. the referenced record's id. */
  key: string;
  /** Text shown in the chip. */
  label: string;
  /** Palette slot to tint the chip with. Omit for the neutral glass chip. */
  color?: TagColor;
  /** Longer free text shown in the chip's hover tooltip. */
  description?: string;
}

/** Props for {@link ChipRow}. */
interface ChipRowProps {
  /** Chips to show, in order. The overflow is taken off the end. */
  items: ChipRowItem[];
  /**
   * Heading for the "show everything" dialog the `+N` chip opens, and the noun
   * in that chip's accessible name (`Show all N <title lowercased>`).
   */
  title?: string;
}

/** Gap between chips in pixels. Mirrors the row's `gap-1`. */
const GAP = 4;

/** Horizontal padding a chip spends on itself (`px-2`), in pixels. */
const CHIP_PADDING_X = 16;

/**
 * Width of one character in the chip's `text-xs` mono face, in pixels.
 *
 * JetBrains Mono at 12px advances ~7.2px; rounded up so every derived width is
 * an upper bound rather than a hair short.
 */
const MONO_CHAR_WIDTH = 8;

/**
 * Width to reserve for the `+N` chip, in pixels.
 *
 * Derived rather than measured: the chip does not exist until the fit has
 * already decided something overflows, so measuring it would need a further
 * layout pass. `count` is the total number of chips, which bounds the digits
 * `N` can ever reach — so the reservation is tight even before the fold size is
 * known. A flat constant generous enough for the widest count would cost a
 * borderline row one chip it had room for.
 *
 * @param count - How many chips the row holds in total.
 * @returns Pixels the `+N` chip can occupy at most.
 */
function overflowChipWidth(count: number): number {
  return CHIP_PADDING_X + (String(count).length + 1) * MONO_CHAR_WIDTH;
}

/**
 * How many of `widths` fit in `available`, counting the gaps between them.
 *
 * @param widths - Chip widths in pixels, in display order.
 * @param available - Pixels the row may occupy.
 * @returns The number of leading chips that fit, possibly `0`.
 */
function countThatFit(widths: number[], available: number): number {
  let used = 0;
  for (let i = 0; i < widths.length; i++) {
    const next = used + (i > 0 ? GAP : 0) + widths[i];
    if (next > available) return i;
    used = next;
  }
  return widths.length;
}

/**
 * Row of chips capped to a single line, with the overflow collapsed into a
 * neutral `+N` chip. That chip is a button: clicking it opens a modal dialog
 * that lists *every* chip in the row (not just the folded ones), each rendered
 * with its own description-on-hover tooltip.
 *
 * A table cell is the reason this exists. Left to wrap, a row of chips makes
 * row height a function of the data — a record with eight tags stands three
 * lines tall beside a record with one — and the column claims its full
 * max-content width, squeezing every other column (see DESIGN.md → Data
 * Tables). Clipping to one line and counting the remainder holds the row height
 * constant and lets the column give ground like a text column: the `+N` fold
 * *is* this cell's ellipsis, which is why a column rendering one is declared
 * `shrinkable` rather than merely `noTruncate`.
 *
 * The fit is measured, not guessed, so the count follows the width the column
 * actually has: widening it brings chips back, narrowing it raises `N`. Chip
 * widths are measured once — from a first pass that renders every chip, before
 * any is folded away — and cached, the same measure-once-then-refit shape
 * {@link DataTable} uses for its own columns: a chip's width depends only on
 * its label (and `Chip`'s own `max-w-64` cap), so a resize need only re-run the
 * arithmetic, and a folded chip is never re-measured as zero.
 *
 * A container that measures `0` — not laid out yet — shows everything rather
 * than nothing, matching `fitColumnWidths`' own `if (!available)` guard. A
 * column too narrow for even one whole chip shows the count alone: a pill
 * clipped mid-label names its tag no better than `+8` does, and letting it
 * overflow would push the count itself out of the cell.
 *
 * Folded chips are unmounted, so their labels are handed back to assistive
 * technology in an `sr-only` span listing *only* the folded ones — a
 * screen-reader user hears them without having to open the dialog.
 */
export function ChipRow({ items, title = "Details" }: ChipRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const [open, setOpen] = useState(false);
  // Mount the dialog only once it has been opened, then keep it mounted so its
  // leave animation has a live component to run on. One `ChipRow` per row, so an
  // unconditional dialog would be one idle portal subtree per table row.
  const [everOpened, setEverOpened] = useState(false);
  // Natural chip widths, measured from the all-visible pass and reused by every
  // refit. `null` until that pass has run for the current chips.
  const widthsRef = useRef<number[] | null>(null);
  const [visibleCount, setVisibleCount] = useState(items.length);

  // A column's `cell` rebuilds `items` inline on every render, so its identity
  // is worthless as a dependency; the labels (and how many there are) are what
  // the measured widths actually depend on.
  const itemsKey = `${items.length}:${items.map((item) => item.label).join("\u0000")}`;
  const [measuredKey, setMeasuredKey] = useState(itemsKey);

  // Reset to the all-visible pass during render rather than in an effect: the
  // measurement below has to see every chip, and an effect-driven reset would
  // let a commit carrying the *previous* fit's survivors be measured first.
  if (measuredKey !== itemsKey) {
    setMeasuredKey(itemsKey);
    setVisibleCount(items.length);
    widthsRef.current = null;
  }

  const refit = useCallback(() => {
    const widths = widthsRef.current;
    if (!widths) return;
    const available = rowRef.current?.clientWidth ?? 0;
    // Not laid out yet: show everything rather than folding away chips nobody
    // has had a chance to see.
    if (!available) {
      setVisibleCount(widths.length);
      return;
    }
    const all = countThatFit(widths, available);
    if (all === widths.length) {
      setVisibleCount(all);
      return;
    }
    // Something is folding, so the `+N` chip has to fit alongside the rest.
    // Only chips that fit *whole* are shown: a partly-clipped pill would be the
    // one thing to spill past `overflow-hidden`, and what it would push out is
    // the count itself — the one mark that says there is more to see.
    setVisibleCount(countThatFit(widths, available - overflowChipWidth(widths.length) - GAP));
  }, []);

  // Measure from the commit that rendered every chip, then fit. A layout effect
  // so the fold lands before paint — a flash of the full row would be exactly
  // the reflow this component exists to prevent.
  // biome-ignore lint/correctness/useExhaustiveDependencies: itemsKey captures the relevant change
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    widthsRef.current = [...row.children].map((child) => (child as HTMLElement).offsetWidth);
    refit();
  }, [itemsKey, refit]);

  useEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    const observer = new ResizeObserver(refit);
    observer.observe(row);
    return () => observer.disconnect();
  }, [refit]);

  const shown = items.slice(0, visibleCount);
  const hidden = items.slice(visibleCount);

  return (
    <>
      {/* Deliberately no `w-full`: a percentage width contributes nothing to a
          cell's max-content, which would collapse the column's *natural* width
          to its header label and leave the fit no reason ever to grant the
          chips room. A plain block div already fills the cell, and measures as
          the full row of chips while the table is still laying out naturally. */}
      <div ref={rowRef} className="flex items-center gap-1 overflow-hidden">
        {shown.map((item) => (
          <Chip
            key={item.key}
            label={item.label}
            color={item.color}
            description={item.description}
          />
        ))}
        {hidden.length > 0 && (
          <>
            {/* No `color` on the count itself, so it reads as chrome rather than
                as one more tag. It is a button: clicking it opens the dialog
                below, the one place the folded tags' descriptions can be read
                on hover. */}
            <Chip
              label={`+${hidden.length}`}
              ariaLabel={`Show all ${items.length} ${title.toLowerCase()}`}
              onClick={() => {
                setEverOpened(true);
                setOpen(true);
              }}
            />
            <span className="sr-only">{hidden.map((i) => i.label).join(", ")}</span>
          </>
        )}
      </div>
      {everOpened && (
        <Dialog
          open={open}
          onClose={() => setOpen(false)}
          panelId={panelId}
          title={title}
          size="md"
          scrollable
          footer={
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
          }
        >
          <div className="flex-1 overflow-y-auto">
            <div className="flex flex-wrap gap-2">
              {items.map((item) => (
                <Chip
                  key={item.key}
                  label={item.label}
                  color={item.color}
                  description={item.description}
                />
              ))}
            </div>
          </div>
        </Dialog>
      )}
    </>
  );
}
