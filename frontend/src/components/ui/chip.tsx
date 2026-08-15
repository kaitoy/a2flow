/** @module Chip — single-line data pill for variable-length labels, with an overflow tooltip. */
"use client";

import { Check, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { TagColor } from "@/lib/api";
import { TAG_COLOR_CLASS } from "@/lib/tag-palette";
import { Tooltip } from "./tooltip";

/** Props for {@link Chip}. */
interface ChipProps {
  /** Text shown in the chip; clipped to one line and revealed in full on hover. */
  label: string;
  /**
   * Palette slot to tint the chip with. Omit for the neutral `glass-panel`
   * chip every non-tag caller uses; pass a slot to render a tag, which draws
   * its fill, border, and text from that slot's hue instead.
   */
  color?: TagColor;
  /** Called when the pointer enters the chip. */
  onMouseEnter?: () => void;
  /** Called when the pointer leaves the chip. */
  onMouseLeave?: () => void;
  /**
   * When supplied, the chip renders a trailing remove button labelled
   * `Remove ${label}` — a 20px round icon target that borders and tints
   * `error` on hover/focus. Omit it for chips that only display a reference.
   */
  onRemove?: () => void;
  /**
   * When supplied, the whole chip becomes a toggle button reporting its state
   * through `aria-pressed`. Mutually exclusive with {@link ChipProps.onRemove}:
   * a chip cannot both be a button and contain one.
   */
  onToggle?: () => void;
  /**
   * Pressed state of the toggle. Ignored without {@link ChipProps.onToggle}.
   */
  selected?: boolean;
  /**
   * Pill dimensions. Defaults to `"sm"`, the compact data-pill size every
   * other caller wants. Pass `"lg"` where the chip sits beside a full-size
   * form control (e.g. {@link SecretRefField}'s secret chip next to its
   * entry `Select`) and the default reads as visually undersized next to it.
   */
  size?: "sm" | "lg";
}

/**
 * Class list for the remove button.
 *
 * Hand-rolled rather than reusing {@link DeleteIconButton} or
 * {@link ActionIconButton}: both are `size-8` and carry a `glass-panel`
 * surface of their own, which is far too large and stacks a second glass tier
 * inside this pill (itself a `glass-panel`) at `py-0.5 text-xs`. There is no
 * shared small icon button to reach for, so this matches the shared
 * conventions by hand instead — `cursor-pointer`, the standard
 * `focus-visible:ring-2` treatment (DESIGN.md → Accessibility), and the motion
 * duration/ease tokens rather than a bare `transition-colors`.
 *
 * The border is reserved at rest as `border-transparent` so the hover outline
 * appears without nudging the layout, and the `error` palette is borrowed from
 * `DeleteIconButton` because removing an assignment is the same destructive
 * verb.
 */
const REMOVE_BUTTON_CLASS = [
  // 20px round hit target. The `sm` pill pads `px-2`; `-mr-1` pulls the
  // button back into that padding so the trailing gap stays visually even
  // (the `lg` pill's wider `px-4` leaves a bit more air, which is fine —
  // that size exists to look substantial next to a full-size form control).
  "-mr-1 ml-1 inline-flex size-5 shrink-0 items-center justify-center rounded-full",
  // DESIGN.md → Responsive & touch puts icon buttons at ~44px under
  // `pointer-coarse`. Deliberately smaller here: 44px inside a `text-xs` pill
  // would take the whole chip to ~48px tall. 28px is the compromise.
  "pointer-coarse:size-7",
  "cursor-pointer border border-transparent text-on-surface-variant",
  // `translate`/`scale` must be named for the `active:scale-90` below to
  // animate — Tailwind v4 drives transforms through separate properties.
  "transition-[background-color,border-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
  "hover:border-error/40 hover:bg-error/10 hover:text-error",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error/50",
  "motion-safe:active:scale-90",
].join(" ");

/**
 * Shape shared by both roots, so the toggle button and the plain pill are the
 * same object with a different element under it.
 */
const PILL = "inline-flex max-w-64 items-center rounded-md font-mono";

/**
 * Padding and type scale per {@link ChipProps.size}. `lg`'s `px-4 py-2.5
 * text-sm` mirrors {@link Select}'s `TRIGGER_BASE` padding and type scale so a
 * chip standing in for a chosen value lands at the same height as the control
 * beside it.
 */
const SIZE: Record<"sm" | "lg", string> = {
  sm: "px-2 py-0.5 text-xs",
  lg: "px-4 py-2.5 text-sm",
};

/**
 * Extra classes carried only by a chip in toggle mode.
 *
 * Matches the shared conventions rather than inventing a pressable style: the
 * house `focus-visible:ring-2` treatment (DESIGN.md → Accessibility) and the
 * motion duration/ease tokens. `scale` is named in the transition property list
 * because Tailwind v4 drives transforms through separate custom properties, so
 * `transition-colors` alone would leave `active:scale` un-animated — the same
 * reason {@link REMOVE_BUTTON_CLASS} names it.
 */
const TOGGLE_CLASS = [
  "cursor-pointer text-left",
  "transition-[background-color,border-color,color,box-shadow,transform,translate,scale]",
  "duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
  "motion-safe:active:scale-[0.97]",
].join(" ");

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
 * that represent a dismissible selection rather than a plain reference. It is
 * sized and styled as a real icon button (see {@link REMOVE_BUTTON_CLASS}), so
 * a chip carrying one stands 4px taller than a plain reference chip.
 *
 * Pass {@link ChipProps.onToggle} instead to make the *whole* chip a toggle
 * button — how {@link TagPickerDialog} offers the tenant's vocabulary. The root
 * element becomes a `<button aria-pressed>`, which is why the two props are
 * mutually exclusive: `onRemove`'s button cannot nest inside it. A pressed chip
 * takes `.tag-chip-selected` *and* a leading check, so the state is never
 * carried by color alone. The pressed fill derives from the palette slot, so a
 * toggle chip is expected to carry a {@link ChipProps.color}; without one only
 * the check distinguishes it.
 */
export function Chip({
  label,
  color,
  onMouseEnter,
  onMouseLeave,
  onRemove,
  onToggle,
  selected = false,
  size = "sm",
}: ChipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  // A colored chip swaps the neutral glass surface for the slot's tint rather
  // than layering one over the other: stacking a translucent hue on translucent
  // glass muddies the color differently on every background it floats over.
  const surface = color
    ? `tag-chip ${TAG_COLOR_CLASS[color]}`
    : "glass-panel text-on-surface-variant";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Shared by both roots so the pill's contents — and the ref the overflow
  // measurement above hangs off — are written once.
  const body = (
    <>
      {onToggle && selected && (
        // `strokeWidth` is raised above the house 1.8 for the same reason the
        // remove icon raises it: at 14px the lighter stroke reads as a hairline.
        <Check size={14} strokeWidth={2} aria-hidden="true" className="-ml-0.5 mr-1 shrink-0" />
      )}
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
          className={REMOVE_BUTTON_CLASS}
        >
          {/* `strokeWidth` is raised above the house 1.8 (DESIGN.md →
              Iconography): at 14px the lighter stroke reads as a hairline. */}
          <X size={14} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    </>
  );

  if (onToggle) {
    return (
      <button
        type="button"
        aria-pressed={selected}
        onClick={onToggle}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        className={`${PILL} ${SIZE[size]} ${surface} ${selected ? "tag-chip-selected " : ""}${TOGGLE_CLASS}`}
      >
        {body}
      </button>
    );
  }

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: hover is a non-essential visual link to the referenced row; the chip's text is the accessible content
    <span
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={`${PILL} ${SIZE[size]} ${surface}`}
    >
      {body}
    </span>
  );
}
