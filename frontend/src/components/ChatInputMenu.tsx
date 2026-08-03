/** @module ChatInputMenu — "+" dropdown in the chat input for extra, page-specific chat actions; currently a single "Generate description" item. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { Plus, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

/** Props for {@link ChatInputMenu}. */
interface ChatInputMenuProps {
  /** Re-summarizes the design conversation into the workflow's generated description. */
  onGenerateDescription: () => void;
  /** Disables the "Generate description" item (e.g. while the workflow's task templates are still generating). */
  disabled?: boolean;
  /** Shows a spin animation on the item's icon while the generate request is in flight. */
  pending?: boolean;
}

/** Preferred width of the dropdown panel in pixels. */
const PANEL_WIDTH = 200;
const GAP = 8;
const EDGE_PADDING = 8;

interface Coords {
  bottom: number;
  left: number;
  /** Rendered panel width, clamped to the viewport. */
  width: number;
}

/**
 * Small "+" trigger opening a glass dropdown above the chat input. The chat
 * input sits at the bottom of the viewport, so — unlike `UserMenu` and
 * `TableHeaderMenu`, which open downward — this panel is anchored to its own
 * `bottom` edge and grows upward. Self-contained (owns its `open` state and
 * portals its panel to `document.body`) since it has a single call site,
 * following `TableHeaderMenu`'s pattern rather than `UserMenu`'s
 * externally-driven one.
 */
export function ChatInputMenu({
  onGenerateDescription,
  disabled = false,
  pending = false,
}: ChatInputMenuProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const config = useMotionConfig("snappy");

  const computeCoords = useCallback((): Coords | null => {
    const anchor = buttonRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    // Shrink below the preferred width on viewports too narrow to fit it.
    const width = Math.min(PANEL_WIDTH, window.innerWidth - EDGE_PADDING * 2);
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.left, window.innerWidth - width - EDGE_PADDING)
    );
    return { bottom: window.innerHeight - rect.top + GAP, left, width };
  }, []);

  // Track the anchor position while open.
  useEffect(() => {
    if (!open) return;
    setCoords(computeCoords());
    const onChange = () => setCoords(computeCoords());
    window.addEventListener("scroll", onChange, true);
    window.addEventListener("resize", onChange);
    return () => {
      window.removeEventListener("scroll", onChange, true);
      window.removeEventListener("resize", onChange);
    };
  }, [open, computeCoords]);

  useDialogA11y({
    open,
    onClose: () => setOpen(false),
    anchorRef: buttonRef,
    panelId: "chat-input-menu",
    ready: coords !== null,
  });

  const transitions = useTransition(open, {
    from: { opacity: 0, y: 6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: 6 },
    config,
  });

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Chat actions"
        onClick={() => setOpen((o) => !o)}
        className="glass-panel flex size-9 shrink-0 self-end items-center justify-center rounded-xl cursor-pointer text-on-surface-variant transition-[background-color,border-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)] hover:border-accent/40 hover:bg-accent/10 hover:text-accent motion-safe:hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <Plus size={18} strokeWidth={1.8} aria-hidden="true" />
      </button>
      {typeof document !== "undefined" &&
        createPortal(
          transitions(
            (style, isOpen) =>
              isOpen &&
              coords && (
                <animated.div
                  id="chat-input-menu"
                  role="menu"
                  tabIndex={-1}
                  aria-label="Chat actions menu"
                  style={{
                    position: "fixed",
                    bottom: coords.bottom,
                    left: coords.left,
                    width: coords.width,
                    opacity: style.opacity,
                    transform: style.y.to((y) => `translateY(${y}px)`),
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay rounded-xl p-2 text-on-surface"
                >
                  <button
                    type="button"
                    role="menuitem"
                    disabled={disabled}
                    onClick={() => {
                      onGenerateDescription();
                      setOpen(false);
                    }}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Sparkles
                      size={16}
                      strokeWidth={1.8}
                      aria-hidden="true"
                      className={pending ? "motion-safe:animate-spin-y" : undefined}
                    />
                    Generate description
                  </button>
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
