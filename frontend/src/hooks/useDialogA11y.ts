"use client";

import { type RefObject, useEffect, useRef } from "react";

/** Selector matching the elements considered focusable inside a trapped panel. */
const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** Options for {@link useDialogA11y}. */
export interface UseDialogA11yOptions {
  /** Whether the panel is currently open. */
  open: boolean;
  /** Called to close the panel (Escape, or an outside pointerdown when enabled). */
  onClose: () => void;
  /** DOM id of the panel's root element. */
  panelId: string;
  /**
   * The trigger element the panel anchors to; clicks inside it don't count as
   * "outside". Omit for centered modals with their own backdrop (pass
   * `closeOnOutsideClick: false` in that case).
   */
  anchorRef?: RefObject<HTMLElement | null>;
  /**
   * Whether the panel's root node is actually in the DOM. Anchored popovers
   * commonly gate their first paint behind an async-computed position — pass
   * that signal (e.g. `coords !== null`) so this hook doesn't try to focus
   * into a node that doesn't exist yet. Defaults to `true`.
   */
  ready?: boolean;
  /**
   * Whether to close on an outside pointerdown. Set `false` when the caller
   * already has its own backdrop-click handling (e.g. modal dialogs), to
   * avoid a redundant second close mechanism. Defaults to `true`.
   */
  closeOnOutsideClick?: boolean;
}

/**
 * Shared accessibility wiring for anchored popovers and modal dialogs: moves
 * focus into the panel on open, traps Tab navigation within it while open,
 * closes on Escape (and optionally on an outside pointerdown), and restores
 * focus to the trigger on close.
 */
export function useDialogA11y({
  open,
  onClose,
  panelId,
  anchorRef,
  ready = true,
  closeOnOutsideClick = true,
}: UseDialogA11yOptions): void {
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // Capture the trigger and move focus into the panel when it opens;
  // restore focus to the trigger when it closes, unless something else has
  // already legitimately claimed focus in the meantime.
  useEffect(() => {
    if (!open || !ready) return;
    const panel = document.getElementById(panelId);
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const focusable = panel?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusable?.[0] ?? panel)?.focus();

    return () => {
      const anchor = restoreFocusRef.current;
      // The browser's own default mousedown focus/blur step for whatever was
      // clicked hasn't run yet at this point — it's a later dispatch within
      // the same gesture. Defer one microtask so that settles first.
      queueMicrotask(() => {
        const current = document.getElementById(panelId);
        const active = document.activeElement;
        const nothingElseClaimedFocus =
          active === null || active === document.body || !!current?.contains(active);
        if (nothingElseClaimedFocus) anchor?.focus();
      });
    };
  }, [open, ready, panelId]);

  // Close on Escape or (optionally) a click outside both the panel and its
  // anchor; trap Tab focus within the panel while open.
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const current = document.getElementById(panelId);
      if (!current) return;
      const items = current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      const first = items[0] ?? current;
      const last = items[items.length - 1] ?? current;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    function handlePointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (anchorRef?.current?.contains(target)) return;
      if (document.getElementById(panelId)?.contains(target)) return;
      onClose();
    }

    window.addEventListener("keydown", handleKeyDown);
    if (closeOnOutsideClick) window.addEventListener("pointerdown", handlePointerDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      if (closeOnOutsideClick) window.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [open, onClose, anchorRef, panelId, closeOnOutsideClick]);
}
