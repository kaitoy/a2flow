"use client";

import { animated } from "@react-spring/web";
import { useSlidingIndicator } from "@/hooks/useSlidingIndicator";
import type { SpringPreset } from "@/lib/motion";

/** Props for {@link SlidingIndicator}. */
export interface SlidingIndicatorProps {
  /** Map from item key to element. Looked up freshly during measurement. */
  itemMap: React.RefObject<Map<string, HTMLElement | null>>;
  /** Key of the active item in {@link itemMap}, or `null` to hide the bar. */
  activeKey: string | null;
  /** Extra triggers that should re-run measurement (e.g. list contents, pathname). */
  deps?: ReadonlyArray<unknown>;
  /** Spring preset to use (defaults to `gentle`). */
  preset?: SpringPreset;
}

/**
 * Vertical accent bar that springs between candidate items to visualize the
 * current selection. Render this as a direct child of the element that should
 * serve as the bar's positioning context (must be `position: relative`); the
 * bar derives the container from its own DOM parent so it works correctly on
 * first mount, before the parent's React ref has been attached.
 *
 * The measurement itself lives in {@link useSlidingIndicator}, shared with the
 * horizontal selection pill of `SegmentedControl`.
 */
export function SlidingIndicator({
  itemMap,
  activeKey,
  deps = [],
  preset = "gentle",
}: SlidingIndicatorProps) {
  const { ref, offset, size, opacity } = useSlidingIndicator({
    itemMap,
    activeKey,
    deps,
    preset,
    axis: "vertical",
    // Two thirds of the item's height, so the bar reads as a marker beside the
    // item rather than a full-height fill.
    extent: 2 / 3,
  });

  return (
    <animated.span
      ref={ref}
      aria-hidden="true"
      style={{
        transform: offset.to((y) => `translateY(${y}px)`),
        height: size,
        opacity,
      }}
      className="pointer-events-none absolute left-0 top-0 w-[3px] rounded-r-full bg-accent shadow-glow"
    />
  );
}
