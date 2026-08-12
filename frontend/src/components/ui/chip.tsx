/** @module Chip — single-line data pill for variable-length labels, with an overflow tooltip. */
"use client";

import { useEffect, useRef, useState } from "react";
import { Tooltip } from "./tooltip";

/** Props for {@link Chip}. */
interface ChipProps {
  /** Text shown in the chip; clipped to one line and revealed in full on hover. */
  label: string;
  /** Called when the pointer enters the chip. */
  onMouseEnter?: () => void;
  /** Called when the pointer leaves the chip. */
  onMouseLeave?: () => void;
  /**
   * When supplied, the chip renders a remove button labelled
   * `Remove ${label}`. Omit it for chips that only display a reference.
   */
  onRemove?: () => void;
}

/**
 * Pill naming a single related record (a dependency task, a bound MCP tool) in
 * the mono data face.
 *
 * The label is arbitrary user/agent-authored text, so the chip caps its width
 * and clips to one line: left to wrap, a long title breaks the pill open —
 * `rounded-full`'s radius grows to half the box height and swallows the first
 * and last lines' text. Hence the modest `rounded-md` and the hard `max-w-64`
 * on the outer pill (see DESIGN.md → Shapes) — 16rem, sized to clear the
 * 30-character title the design agent is held to, so only a genuinely runaway
 * label ever clips.
 *
 * Truncation lives on an *inner* span wrapping only the label text, not the
 * whole pill: with {@link ChipProps.onRemove} set, the pill also renders a
 * trailing remove button, and a single `truncate` box spanning label + button
 * would clip the button itself out of the layout (and out of the hit-test
 * area) once the label ran long enough. Splitting them — `min-w-0 truncate`
 * on the label span, `shrink-0` on the button, both inside an `inline-flex`
 * pill — keeps the button reachable at any label length while the label alone
 * still clips to the space the pill's `max-w-64` leaves it.
 *
 * The full label text is revealed in a tooltip, and only when it is actually
 * clipped: overflow is measured from the DOM (`scrollWidth > clientWidth`) on
 * the same inner label span that truncates, re-measured on resize, the same
 * way {@link TruncatedCell} does it.
 *
 * `Tooltip` composes its own ref and hover handlers onto the child element, so
 * it wraps the inner label `<span>` here rather than the caller wrapping
 * `<Chip>` — cloning a component instead of a DOM element would drop both —
 * and rather than the outer pill, which is what keeps the tooltip's trigger
 * area matched to the exact box that clips.
 *
 * Pass {@link ChipProps.onRemove} to add a trailing remove button for chips
 * that represent a dismissible selection rather than a plain reference.
 */
export function Chip({ label, onMouseEnter, onMouseLeave, onRemove }: ChipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: hover is a non-essential visual link to the referenced row; the chip's text is the accessible content
    <span
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="inline-flex max-w-64 items-center rounded-md glass-panel px-2 py-0.5 font-mono text-xs text-on-surface-variant"
    >
      <Tooltip label={label} disabled={!overflowing}>
        <span ref={ref} className="min-w-0 truncate">
          {label}
        </span>
      </Tooltip>
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${label}`}
          onClick={onRemove}
          className="ml-1 shrink-0 text-on-surface-variant transition-colors hover:text-error"
        >
          ×
        </button>
      )}
    </span>
  );
}
