/**
 * @module useSlidingIndicator — Spring-driven geometry for an indicator that
 * travels between sibling items along a single axis.
 *
 * Both the admin sidebar's 3px active bar and the segmented control's selection
 * pill need the same non-obvious wiring: derive the positioning context from the
 * indicator's own DOM parent (so measurement is correct on first mount, before a
 * parent's React ref has attached), re-measure whenever the container or any
 * item resizes, place the very first position without animating it in, and honor
 * `prefers-reduced-motion`. That geometry lives here once; each consumer supplies
 * only its axis, extent, and appearance.
 */
"use client";

import { type SpringValue, useSpring } from "@react-spring/web";
import { useLayoutEffect, useRef } from "react";
import { type SpringPreset, useMotionConfig } from "@/lib/motion";

/** Axis along which the indicator travels. */
export type SlidingAxis = "vertical" | "horizontal";

/** Options for {@link useSlidingIndicator}. */
export interface UseSlidingIndicatorOptions {
  /** Map from item key to element. Looked up freshly during measurement. */
  itemMap: React.RefObject<Map<string, HTMLElement | null>>;
  /** Key of the active item in {@link itemMap}, or `null` to hide the indicator. */
  activeKey: string | null;
  /** Axis the indicator travels along (defaults to `vertical`). */
  axis?: SlidingAxis;
  /**
   * Fraction of the target's extent along {@link axis} that the indicator spans,
   * centered on the target. `1` matches the target exactly; the sidebar bar uses
   * `2 / 3` so it reads as a marker rather than a full-height fill.
   */
  extent?: number;
  /** Extra triggers that should re-run measurement (e.g. list contents, pathname). */
  deps?: ReadonlyArray<unknown>;
  /** Spring preset to use (defaults to `gentle`). */
  preset?: SpringPreset;
}

/** Where the indicator sits along its axis, in px relative to the container. */
export interface IndicatorGeometry {
  /** Distance from the container's start edge along the axis. */
  offset: number;
  /** Indicator size along the axis. */
  size: number;
}

/**
 * Project the active item's rect into the container's coordinate space along a
 * single axis, centering an indicator of `extent` × the item's size on it.
 *
 * @param container - The indicator's positioning context.
 * @param target - The currently active item.
 * @param axis - Axis the indicator travels along.
 * @param extent - Fraction of the target's extent the indicator spans.
 * @returns The indicator's offset and size along `axis`.
 */
export function measureIndicator(
  container: HTMLElement,
  target: HTMLElement,
  axis: SlidingAxis,
  extent: number
): IndicatorGeometry {
  const c = container.getBoundingClientRect();
  const t = target.getBoundingClientRect();
  const full = axis === "vertical" ? t.height : t.width;
  const start =
    axis === "vertical"
      ? t.top - c.top + container.scrollTop
      : t.left - c.left + container.scrollLeft;
  const size = full * extent;
  return { offset: start + (full - size) / 2, size };
}

/** Animated values returned by {@link useSlidingIndicator}. */
export interface SlidingIndicatorState {
  /**
   * Attach to the animated indicator element. Its DOM parent is used as the
   * positioning context, so that parent must be `position: relative`.
   */
  ref: React.RefObject<HTMLSpanElement | null>;
  /** Distance in px from the container's start edge along the axis. */
  offset: SpringValue<number>;
  /** Indicator size in px along the axis. */
  size: SpringValue<number>;
  /** `0` while there is no active item, `1` otherwise. */
  opacity: SpringValue<number>;
}

/**
 * Measure the active item and spring an indicator to it.
 *
 * @param options - Item map, active key, axis, and motion configuration.
 * @returns The ref to attach to the indicator plus its animated offset/size/opacity.
 */
export function useSlidingIndicator({
  itemMap,
  activeKey,
  axis = "vertical",
  extent = 1,
  deps = [],
  preset = "gentle",
}: UseSlidingIndicatorOptions): SlidingIndicatorState {
  const config = useMotionConfig(preset);
  const firstMountRef = useRef(true);
  const ref = useRef<HTMLSpanElement>(null);
  const [style, api] = useSpring(() => ({
    offset: 0,
    size: 0,
    opacity: 0,
    config,
  }));

  useLayoutEffect(() => {
    const container = ref.current?.parentElement ?? null;
    const target = activeKey !== null ? (itemMap.current?.get(activeKey) ?? null) : null;

    if (!container || !target) {
      api.start({ opacity: 0, immediate: firstMountRef.current, config });
      firstMountRef.current = false;
      return;
    }

    const measure = () => {
      api.start({
        ...measureIndicator(container, target, axis, extent),
        opacity: 1,
        immediate: firstMountRef.current,
        config,
      });
      firstMountRef.current = false;
    };

    measure();

    const ro = new ResizeObserver(measure);
    ro.observe(container);
    for (const item of itemMap.current?.values() ?? []) {
      if (item) ro.observe(item);
    }

    return () => ro.disconnect();
  }, [activeKey, api, axis, config, extent, itemMap, ...deps]);

  return { ref, offset: style.offset, size: style.size, opacity: style.opacity };
}
