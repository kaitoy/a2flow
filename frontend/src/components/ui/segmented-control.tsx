"use client";

import { animated } from "@react-spring/web";
import type { LucideIcon } from "lucide-react";
import { useRef } from "react";
import { useSlidingIndicator } from "@/hooks/useSlidingIndicator";

/** A single selectable option within a {@link SegmentedControl}. */
export interface SegmentedOption<T extends string> {
  /** Value reported to `onChange` when this option is selected. */
  value: T;
  /** Visible label for the option. */
  label: string;
  /**
   * Optional leading icon. Use one only when it genuinely distinguishes the
   * options (e.g. Globe vs Terminal) — a decorative icon on every segment just
   * adds noise.
   */
  icon?: LucideIcon;
}

/** Props for {@link SegmentedControl}. */
export interface SegmentedControlProps<T extends string> {
  /** Selectable options, rendered left to right. */
  options: ReadonlyArray<SegmentedOption<T>>;
  /** Currently selected value. */
  value: T;
  /** Called with the new value when the user selects a different option. */
  onChange: (value: T) => void;
  /** Accessible label describing what the control switches between. */
  "aria-label": string;
  /** Optional extra class names for the container. */
  className?: string;
}

/**
 * The track: a recessed well rather than a raised glass surface. This is what
 * keeps the control from reading as a filled-in text input — `Input` uses the
 * same `glass-panel` fill, so a raised pill sitting between two inputs looks
 * like a third one.
 */
const TRACK =
  // `w-fit` is load-bearing: `FormField` stacks its children in a column flex
  // container, whose default `align-items: stretch` would otherwise blow the
  // track out to the full form width — exactly the shape of the inputs above
  // and below it.
  "relative inline-flex w-fit gap-1 rounded-full p-1 " +
  "border border-outline-variant bg-surface-dim/40 " +
  "shadow-[inset_0_1px_3px_var(--inner-track-shadow)]";

/**
 * `z-10` lifts the labels above the sliding pill. Scale is listed explicitly in
 * the transition property list — Tailwind v4 composes transforms from separate
 * custom properties, so `transition-colors` alone would not animate the press.
 */
const SEGMENT =
  "relative z-10 inline-flex cursor-pointer items-center gap-1.5 rounded-full " +
  "px-3 py-1.5 text-sm pointer-coarse:px-4 pointer-coarse:py-2.5 " +
  "transition-[scale,background-color,color] " +
  "duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] " +
  "motion-safe:active:scale-[0.97] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50";

/**
 * A compact toggle that switches between a small set of mutually exclusive
 * options (e.g. Table vs Graph, or an MCP server's transport). Implemented as a
 * `tablist` so it is keyboard and screen-reader friendly: arrow keys, Home, and
 * End move the selection, and only the selected segment is a tab stop.
 *
 * The selected segment is marked by an accent pill that springs between options
 * instead of cutting, using the same measurement as the sidebar's active bar
 * (see {@link useSlidingIndicator}).
 *
 * @param props - The options, current value, and change handler.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  "aria-label": ariaLabel,
  className,
}: SegmentedControlProps<T>) {
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  // Call sites pass a fresh array literal every render, so key the measurement
  // off the option values instead — otherwise the ResizeObserver is torn down
  // and rebuilt on every render.
  const optionsKey = options.map((option) => option.value).join("|");

  const { ref, offset, size, opacity } = useSlidingIndicator({
    itemMap,
    activeKey: value,
    axis: "horizontal",
    deps: [optionsKey],
  });

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const current = options.findIndex((option) => option.value === value);
    if (current === -1) return;

    let next: number;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        next = (current + 1) % options.length;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        next = (current - 1 + options.length) % options.length;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = options.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    const target = options[next];
    onChange(target.value);
    itemMap.current.get(target.value)?.focus();
  };

  const containerClass = [TRACK, className].filter(Boolean).join(" ");

  return (
    <div role="tablist" aria-label={ariaLabel} className={containerClass} onKeyDown={handleKeyDown}>
      <animated.span
        ref={ref}
        aria-hidden="true"
        style={{
          transform: offset.to((x) => `translateX(${x}px)`),
          width: size,
          opacity,
        }}
        className="pointer-events-none absolute inset-y-1 left-0 rounded-full bg-accent shadow-glow"
      />
      {options.map((option) => {
        const selected = option.value === value;
        const Icon = option.icon;
        const buttonClass = [
          SEGMENT,
          selected
            ? "text-on-primary"
            : "text-on-surface-variant hover:bg-accent-soft hover:text-on-surface",
        ].join(" ");

        return (
          <button
            key={option.value}
            ref={(el) => {
              if (el) itemMap.current.set(option.value, el);
              else itemMap.current.delete(option.value);
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className={buttonClass}
            onClick={() => onChange(option.value)}
          >
            {Icon && <Icon size={16} strokeWidth={1.8} aria-hidden="true" className="shrink-0" />}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
