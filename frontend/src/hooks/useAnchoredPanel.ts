/** @module useAnchoredPanel — viewport-fitted placement for a portaled panel anchored to a trigger. */
"use client";

import { type RefObject, useCallback, useEffect, useState } from "react";

/** Default distance between the trigger and the panel. */
const DEFAULT_GAP = 6;
/** Default minimum breathing room kept against every viewport edge. */
const DEFAULT_EDGE_PADDING = 8;
/** Default height a side must offer before the panel will open on it. */
const DEFAULT_MIN_HEIGHT = 160;
/**
 * Floor applied to the computed `maxHeight`. On a viewport so short that
 * neither side clears it, a panel that scrolls a little is still usable —
 * a zero-height one is not.
 */
const MIN_VISIBLE_HEIGHT = 120;

/** Options for {@link useAnchoredPanel}. */
export interface UseAnchoredPanelOptions {
  /** Whether the panel is currently open; nothing is measured while closed. */
  open: boolean;
  /** The trigger the panel positions itself against. */
  anchorRef: RefObject<HTMLElement | null>;
  /**
   * Preferred panel width in pixels, or `"anchor"` to match the trigger's own
   * measured width (what a value picker wants, so its popup lines up with the
   * control it belongs to).
   */
  width: number | "anchor";
  /** Floor applied when `width` is `"anchor"`. Defaults to `0`. */
  minWidth?: number;
  /**
   * Horizontal alignment against the trigger: `"start"` lines the panel's left
   * edge up with the trigger's, `"end"` its right edge. Pick `"end"` for a
   * trigger sitting near the viewport's right edge. Defaults to `"start"`.
   */
  align?: "start" | "end";
  /** Distance between the trigger and the panel. Defaults to `6`. */
  gap?: number;
  /** Minimum room kept against every viewport edge. Defaults to `8`. */
  edgePadding?: number;
  /**
   * Height the preferred side must offer before the panel opens on it; below
   * that it flips to the other side. Defaults to `160`.
   */
  minHeight?: number;
  /**
   * Cap on the returned `maxHeight`, so a panel with few items doesn't stretch
   * to fill a tall viewport. Omit to let it use whatever room the chosen side has.
   */
  preferredMaxHeight?: number;
}

/** Where and how large the panel should render, in viewport (`position: fixed`) coordinates. */
export interface AnchoredPanelPosition {
  /** Offset from the viewport's top edge; set when the panel opens downward. */
  top?: number;
  /** Offset from the viewport's bottom edge; set when the panel has flipped upward. */
  bottom?: number;
  /** Offset from the viewport's left edge. */
  left: number;
  /** Rendered panel width, clamped to the viewport. */
  width: number;
  /** Largest height that still fits on the chosen side; the panel must scroll past it. */
  maxHeight: number;
  /** Which side of the trigger the panel ended up on. Drives the enter animation's direction. */
  placement: "bottom" | "top";
}

/**
 * Position a portaled, `position: fixed` panel against its trigger so it always
 * fits on screen.
 *
 * Collects the placement math every anchored popover in the app used to
 * hand-write (see `ColumnPicker`, `Select`): the width is clamped to the
 * viewport, the panel is aligned to one of the trigger's edges and then clamped
 * so neither of its own edges spills out, and the position is recomputed on
 * scroll and resize so the panel tracks its trigger.
 *
 * What the hand-written copies each lacked is the vertical half: the panel
 * opens below the trigger only while that side has room for it, flipping above
 * when it does not, and always reports a `maxHeight` for the side it chose.
 * A panel taller than that must scroll internally — a column picker listing
 * seventeen columns cannot otherwise be reached on a short viewport.
 *
 * Returns `null` until the trigger has been measured (and whenever the panel is
 * closed), which is the signal `useDialogA11y`'s `ready` option expects.
 */
export function useAnchoredPanel({
  open,
  anchorRef,
  width,
  minWidth = 0,
  align = "start",
  gap = DEFAULT_GAP,
  edgePadding = DEFAULT_EDGE_PADDING,
  minHeight = DEFAULT_MIN_HEIGHT,
  preferredMaxHeight,
}: UseAnchoredPanelOptions): AnchoredPanelPosition | null {
  const [position, setPosition] = useState<AnchoredPanelPosition | null>(null);

  const compute = useCallback((): AnchoredPanelPosition | null => {
    const anchor = anchorRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Shrink below the preferred width on viewports too narrow to fit it.
    const available = viewportWidth - edgePadding * 2;
    const panelWidth =
      width === "anchor"
        ? Math.max(minWidth, Math.min(rect.width, available))
        : Math.min(width, available);

    // Align to the requested edge, then clamp so neither of ours spills out.
    const preferredLeft = align === "end" ? rect.right - panelWidth : rect.left;
    const left = Math.max(
      edgePadding,
      Math.min(preferredLeft, viewportWidth - panelWidth - edgePadding)
    );

    const roomBelow = viewportHeight - rect.bottom - gap - edgePadding;
    const roomAbove = rect.top - gap - edgePadding;
    // Prefer opening downward; flip only when that side is genuinely too
    // cramped *and* the other one is roomier, so a panel never jumps sides
    // for a marginal gain.
    const placement: "bottom" | "top" =
      roomBelow < minHeight && roomAbove > roomBelow ? "top" : "bottom";

    const room = placement === "bottom" ? roomBelow : roomAbove;
    const maxHeight = Math.max(
      MIN_VISIBLE_HEIGHT,
      preferredMaxHeight === undefined ? room : Math.min(room, preferredMaxHeight)
    );

    return placement === "bottom"
      ? { top: rect.bottom + gap, left, width: panelWidth, maxHeight, placement }
      : // Anchored from the bottom rather than by a computed top, so a panel
        // shorter than `maxHeight` still sits against the trigger instead of
        // floating away from it.
        {
          bottom: viewportHeight - rect.top + gap,
          left,
          width: panelWidth,
          maxHeight,
          placement,
        };
  }, [anchorRef, width, minWidth, align, gap, edgePadding, minHeight, preferredMaxHeight]);

  useEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    setPosition(compute());
    const reposition = () => setPosition(compute());
    // Capture phase: the trigger may live inside a scrollable panel whose own
    // scroll events never reach the window during the bubble phase.
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open, compute]);

  return position;
}
