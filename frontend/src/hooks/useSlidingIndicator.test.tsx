import { animated } from "@react-spring/web";
import { render, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it } from "vitest";
import {
  measureIndicator,
  type SlidingIndicatorState,
  useSlidingIndicator,
} from "./useSlidingIndicator";

/**
 * Build a detached element with a fixed bounding rect and scroll offsets, since
 * happy-dom reports zeros for every layout measurement.
 */
function elementWith(
  rect: { top?: number; left?: number; width?: number; height?: number },
  scroll: { top?: number; left?: number } = {}
): HTMLElement {
  const el = document.createElement("div");
  const { top = 0, left = 0, width = 0, height = 0 } = rect;
  el.getBoundingClientRect = () =>
    ({
      top,
      left,
      width,
      height,
      right: left + width,
      bottom: top + height,
      x: left,
      y: top,
      toJSON: () => ({}),
    }) as DOMRect;
  Object.defineProperty(el, "scrollTop", { value: scroll.top ?? 0, writable: true });
  Object.defineProperty(el, "scrollLeft", { value: scroll.left ?? 0, writable: true });
  return el;
}

describe("measureIndicator", () => {
  it("projects the target's horizontal rect into the container's space", () => {
    const container = elementWith({ left: 100, width: 300 });
    const target = elementWith({ left: 140, width: 80 });

    expect(measureIndicator(container, target, "horizontal", 1)).toEqual({
      offset: 40,
      size: 80,
    });
  });

  it("adds the container's scroll offset", () => {
    const container = elementWith({ left: 100, width: 300 }, { left: 30 });
    const target = elementWith({ left: 140, width: 80 });

    expect(measureIndicator(container, target, "horizontal", 1).offset).toBe(70);
  });

  it("centers a partial-extent bar on the target (the sidebar's 2/3 bar)", () => {
    const container = elementWith({ top: 0, height: 400 });
    const target = elementWith({ top: 50, height: 36 });

    // 36 * 2/3 = 24, centered inside the item: 50 + (36 - 24) / 2 = 56.
    expect(measureIndicator(container, target, "vertical", 2 / 3)).toEqual({
      offset: 56,
      size: 24,
    });
  });
});

/** Renders the hook against two fixed-width items, exposing its state to the test. */
function Harness({
  activeKey,
  onState,
}: {
  activeKey: string | null;
  onState: (state: SlidingIndicatorState) => void;
}) {
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  const state = useSlidingIndicator({ itemMap, activeKey, axis: "horizontal" });
  onState(state);

  return (
    <div
      ref={(el) => {
        if (el) el.getBoundingClientRect = () => rectOf(0, 200);
      }}
    >
      <animated.span ref={state.ref} data-testid="indicator" />
      <button
        type="button"
        ref={(el) => {
          if (el) el.getBoundingClientRect = () => rectOf(0, 60);
          itemMap.current.set("a", el);
        }}
      >
        A
      </button>
      <button
        type="button"
        ref={(el) => {
          if (el) el.getBoundingClientRect = () => rectOf(60, 90);
          itemMap.current.set("b", el);
        }}
      >
        B
      </button>
    </div>
  );
}

/** Horizontal-only rect helper for {@link Harness}. */
function rectOf(left: number, width: number): DOMRect {
  return {
    top: 0,
    left,
    width,
    height: 30,
    right: left + width,
    bottom: 30,
    x: left,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect;
}

describe("useSlidingIndicator", () => {
  it("measures the active item through the indicator's DOM parent", async () => {
    let state: SlidingIndicatorState | null = null;
    render(
      <Harness
        activeKey="b"
        onState={(s) => {
          state = s;
        }}
      />
    );

    await waitFor(() => {
      expect(state?.size.get()).toBe(90);
      expect(state?.offset.get()).toBe(60);
      expect(state?.opacity.get()).toBe(1);
    });
  });

  it("hides the indicator when there is no active item", async () => {
    let state: SlidingIndicatorState | null = null;
    render(
      <Harness
        activeKey={null}
        onState={(s) => {
          state = s;
        }}
      />
    );

    await waitFor(() => expect(state?.opacity.get()).toBe(0));
  });
});
