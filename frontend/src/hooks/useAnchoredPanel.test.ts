import { act, renderHook } from "@testing-library/react";
import type { RefObject } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { type UseAnchoredPanelOptions, useAnchoredPanel } from "./useAnchoredPanel";

const ORIGINAL_WIDTH = window.innerWidth;
const ORIGINAL_HEIGHT = window.innerHeight;

/** Resize the viewport happy-dom reports, since it has no real one. */
function setViewport(width: number, height: number): void {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: height, configurable: true });
}

/**
 * Build a ref to a detached element with a fixed bounding rect, since happy-dom
 * reports zeros for every layout measurement.
 */
function anchorAt(rect: {
  top: number;
  left: number;
  width: number;
  height: number;
}): RefObject<HTMLElement | null> {
  const el = document.createElement("button");
  el.getBoundingClientRect = () =>
    ({
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON: () => ({}),
    }) as DOMRect;
  return { current: el };
}

/** Render the hook with the defaults most callers use. */
function setup(options: Partial<UseAnchoredPanelOptions> = {}) {
  const anchorRef = options.anchorRef ?? anchorAt({ top: 100, left: 400, width: 36, height: 36 });
  return renderHook(() => useAnchoredPanel({ open: true, anchorRef, width: 220, ...options }));
}

afterEach(() => {
  setViewport(ORIGINAL_WIDTH, ORIGINAL_HEIGHT);
});

describe("useAnchoredPanel", () => {
  it("reports nothing while the panel is closed", () => {
    setViewport(1280, 800);
    const { result } = setup({ open: false });

    expect(result.current).toBeNull();
  });

  it("opens below the trigger when that side has room", () => {
    setViewport(1280, 800);
    const { result } = setup();

    expect(result.current?.placement).toBe("bottom");
    // Trigger bottom (136) plus the default 6px gap.
    expect(result.current?.top).toBe(142);
    expect(result.current?.bottom).toBeUndefined();
  });

  it("flips above the trigger when there is no room below it", () => {
    // A 400px-tall viewport with the trigger near its bottom edge.
    setViewport(1280, 400);
    const { result } = setup({
      anchorRef: anchorAt({ top: 330, left: 400, width: 36, height: 36 }),
    });

    expect(result.current?.placement).toBe("top");
    // Measured from the viewport's bottom edge so a short panel still sits
    // against the trigger: 400 - 330 + 6.
    expect(result.current?.bottom).toBe(76);
    expect(result.current?.top).toBeUndefined();
  });

  it("stays below the trigger when neither side clears the minimum but below is roomier", () => {
    // roomBelow is 150 (under the 160 minimum) but still beats roomAbove's 86,
    // so flipping would only make things worse.
    setViewport(1280, 300);
    const { result } = setup({
      anchorRef: anchorAt({ top: 100, left: 400, width: 36, height: 36 }),
    });

    expect(result.current?.placement).toBe("bottom");
    expect(result.current?.maxHeight).toBe(150);
  });

  it("caps the height at the room its side offers", () => {
    setViewport(1280, 500);
    const { result } = setup({
      anchorRef: anchorAt({ top: 100, left: 400, width: 36, height: 36 }),
    });

    // 500 - 136 (trigger bottom) - 6 (gap) - 8 (edge padding).
    expect(result.current?.maxHeight).toBe(350);
  });

  it("caps the height at preferredMaxHeight when the viewport is taller", () => {
    setViewport(1280, 1200);
    const { result } = setup({ preferredMaxHeight: 420 });

    expect(result.current?.maxHeight).toBe(420);
  });

  it("keeps a usable height on a viewport too short for either side", () => {
    // 60px below, 76px above — the roomier side still can't hold a panel, so
    // the floor takes over rather than returning a sliver.
    setViewport(1280, 200);
    const { result } = setup({
      anchorRef: anchorAt({ top: 90, left: 400, width: 36, height: 36 }),
    });

    expect(result.current?.maxHeight).toBe(120);
  });

  it("right-aligns to the trigger when asked", () => {
    setViewport(1280, 800);
    const { result } = setup({
      align: "end",
      anchorRef: anchorAt({ top: 100, left: 1000, width: 36, height: 36 }),
    });

    // Trigger right edge (1036) minus the panel width.
    expect(result.current?.left).toBe(816);
  });

  it("clamps the panel inside the viewport's horizontal edges", () => {
    setViewport(320, 800);
    const { result } = setup({
      width: 400,
      anchorRef: anchorAt({ top: 100, left: 250, width: 36, height: 36 }),
    });

    // Too narrow for the requested 400: the panel shrinks to 320 - 8 * 2, and
    // its left edge lands on the padding rather than on the trigger.
    expect(result.current?.width).toBe(304);
    expect(result.current?.left).toBe(8);
  });

  it("matches the trigger's own width, with a floor, when asked", () => {
    setViewport(1280, 800);
    const { result } = setup({
      width: "anchor",
      minWidth: 160,
      anchorRef: anchorAt({ top: 100, left: 400, width: 90, height: 40 }),
    });

    expect(result.current?.width).toBe(160);
  });

  it("recomputes when the viewport is resized", () => {
    setViewport(1280, 1000);
    const { result } = setup({
      anchorRef: anchorAt({ top: 700, left: 400, width: 36, height: 36 }),
    });
    expect(result.current?.placement).toBe("bottom");

    act(() => {
      setViewport(1280, 800);
      window.dispatchEvent(new Event("resize"));
    });

    expect(result.current?.placement).toBe("top");
  });
});
