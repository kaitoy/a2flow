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
 * (see DESIGN.md → Shapes) — 16rem, sized to clear the 30-character title the
 * design agent is held to, so only a genuinely runaway label ever clips.
 * The full text is revealed in a tooltip, and only
 * when it is actually clipped: overflow is measured from the DOM
 * (`scrollWidth > clientWidth`) and re-measured on resize, the same way
 * {@link TruncatedCell} does it.
 *
 * `Tooltip` composes its own ref and hover handlers onto the child element, so
 * it wraps the `<span>` here rather than the caller wrapping `<Chip>` — cloning
 * a component instead of a DOM element would drop both.
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
    <Tooltip label={label} disabled={!overflowing}>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: hover is a non-essential visual link to the referenced row; the chip's text is the accessible content */}
      <span
        ref={ref}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        className="inline-block max-w-64 truncate rounded-md glass-panel px-2 py-0.5 font-mono text-xs text-on-surface-variant"
      >
        {label}
        {onRemove && (
          <button
            type="button"
            aria-label={`Remove ${label}`}
            onClick={onRemove}
            className="ml-1 text-on-surface-variant transition-colors hover:text-error"
          >
            ×
          </button>
        )}
      </span>
    </Tooltip>
  );
}
