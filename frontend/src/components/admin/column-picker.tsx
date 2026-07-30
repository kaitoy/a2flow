/** @module ColumnPicker — Header control choosing which of a list table's columns are shown. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { Columns3, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";
import { HeaderIconButton } from "./header-icon-button";

/** Props for {@link ColumnPicker}. */
export interface ColumnPickerProps {
  /** One option per toggleable column, in display order (from `useColumnVisibility`). */
  options: CheckboxOption[];
  /** Headers of the columns currently shown. */
  value: string[];
  /** Called with the next set of shown headers whenever one is toggled. */
  onChange: (next: string[]) => void;
  /** Restores the table's declared default columns. */
  onReset: () => void;
  /** Whether the current selection differs from the defaults; gates the reset action. */
  customized: boolean;
}

const PANEL_WIDTH = 220;
const GAP = 6;
const EDGE_PADDING = 8;

interface Coords {
  top: number;
  left: number;
  /** Rendered panel width, clamped to the viewport. */
  width: number;
}

/** Menu action row styling, mirroring the app's dropdown menu items (see TableHeaderMenu). */
const ITEM_CLASSES =
  "flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent";

/**
 * Trigger and floating panel letting the viewer pick which columns a list table
 * shows, plus a "Reset to default" action returning to the table's declared set.
 *
 * Mounts in an `AdminPageHeader`'s `columnPicker` slot (or, where there is no
 * such header, alongside the section title), and is driven entirely by
 * `useColumnVisibility` — this component owns no visibility state of its own,
 * only the panel's open/closed state.
 *
 * The panel renders through a portal so the page's own overflow can never clip
 * it, right-aligned to the trigger since the trigger sits near the viewport's
 * right edge. It uses the dialog a11y pattern (checkboxes rule out
 * menu-pattern arrow-key semantics) and closes on outside click or Escape.
 * Toggling a column deliberately leaves the panel open, so several columns can
 * be adjusted in one visit.
 */
export function ColumnPicker({ options, value, onChange, onReset, customized }: ColumnPickerProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const config = useMotionConfig("snappy");
  // Unique per instance: a closing panel can still be animating out while the
  // next one mounts, so a fixed id would break getElementById lookups.
  const panelId = `column-picker-${useId()}`;

  const computeCoords = useCallback((): Coords | null => {
    const anchor = buttonRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    // Shrink below the preferred width on viewports too narrow to fit it.
    const width = Math.min(PANEL_WIDTH, window.innerWidth - EDGE_PADDING * 2);
    // Right-aligned to the trigger, then clamped so neither edge spills out.
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.right - width, window.innerWidth - width - EDGE_PADDING)
    );
    return { top: rect.bottom + GAP, left, width };
  }, []);

  useEffect(() => {
    if (!open) return;
    setCoords(computeCoords());
    const onChangePos = () => setCoords(computeCoords());
    window.addEventListener("scroll", onChangePos, true);
    window.addEventListener("resize", onChangePos);
    return () => {
      window.removeEventListener("scroll", onChangePos, true);
      window.removeEventListener("resize", onChangePos);
    };
  }, [open, computeCoords]);

  useDialogA11y({
    open,
    onClose: () => setOpen(false),
    anchorRef: buttonRef,
    panelId,
    ready: coords !== null,
  });

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  return (
    <>
      <HeaderIconButton
        ref={buttonRef}
        label="Columns"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Columns3 size={18} strokeWidth={1.8} aria-hidden="true" />
      </HeaderIconButton>
      {typeof document !== "undefined" &&
        createPortal(
          transitions(
            (style, isOpen) =>
              isOpen &&
              coords && (
                <animated.div
                  id={panelId}
                  role="dialog"
                  tabIndex={-1}
                  aria-label="Column visibility"
                  style={{
                    position: "fixed",
                    top: coords.top,
                    left: coords.left,
                    width: coords.width,
                    opacity: style.opacity,
                    transform: style.y.to((y) => `translateY(${y}px)`),
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay rounded-xl p-2 text-on-surface"
                >
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-on-surface-variant">
                    Columns
                  </div>
                  <CheckboxGroup
                    flush
                    options={options}
                    value={value}
                    onChange={onChange}
                    emptyMessage="Every column is always shown."
                  />
                  <div className="my-1 h-px bg-glass-border" />
                  <button
                    type="button"
                    disabled={!customized}
                    onClick={onReset}
                    className={ITEM_CLASSES}
                  >
                    <RotateCcw size={16} strokeWidth={1.8} aria-hidden="true" />
                    Reset to default
                  </button>
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
