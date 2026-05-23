"use client";

import { animated, useSpring } from "@react-spring/web";
import { useLayoutEffect, useRef } from "react";
import { type SpringPreset, useMotionConfig } from "@/lib/motion";

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
 */
export function SlidingIndicator({
  itemMap,
  activeKey,
  deps = [],
  preset = "gentle",
}: SlidingIndicatorProps) {
  const config = useMotionConfig(preset);
  const firstMountRef = useRef(true);
  const barRef = useRef<HTMLSpanElement>(null);
  const [style, api] = useSpring(() => ({
    y: 0,
    height: 0,
    opacity: 0,
    config,
  }));

  useLayoutEffect(() => {
    const container = barRef.current?.parentElement ?? null;
    const target = activeKey !== null ? (itemMap.current?.get(activeKey) ?? null) : null;

    if (!container || !target) {
      api.start({ opacity: 0, immediate: firstMountRef.current, config });
      firstMountRef.current = false;
      return;
    }

    const measure = () => {
      const c = container.getBoundingClientRect();
      const t = target.getBoundingClientRect();
      const barHeight = t.height * (2 / 3);
      const y = t.top - c.top + (t.height - barHeight) / 2 + container.scrollTop;
      api.start({
        y,
        height: barHeight,
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
  }, [activeKey, api, config, itemMap, ...deps]);

  return (
    <animated.span
      ref={barRef}
      aria-hidden="true"
      style={{
        transform: style.y.to((y) => `translateY(${y}px)`),
        height: style.height,
        opacity: style.opacity,
      }}
      className="pointer-events-none absolute left-0 top-0 w-[3px] rounded-r-full bg-accent shadow-glow"
    />
  );
}
