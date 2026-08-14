/** @module ColumnPicker — Header control choosing which of a list table's columns are shown. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { Columns3, RotateCcw } from "lucide-react";
import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { useAnchoredPanel } from "@/hooks/useAnchoredPanel";
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

/** Option count above which the two-column grid is worth its extra width. */
const GRID_THRESHOLD = 8;
/** Panel width for a list short enough to stay in one column. */
const NARROW_WIDTH = 220;
/** Panel width requested for the two-column grid. */
const WIDE_WIDTH = 420;
/** Width below which the grid's cells get too cramped to read; falls back to one column. */
const GRID_MIN_WIDTH = 360;
/** Cap on the panel's height, so a short list doesn't stretch down a tall screen. */
const MAX_PANEL_HEIGHT = 420;

/** Menu action row styling, mirroring the app's dropdown menu items (see TableHeaderMenu). */
const ITEM_CLASSES =
  "flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent";

/** The panel's section label, and the type the bulk toggle matches it with. */
const LABEL_CLASSES = "text-[11px] font-semibold uppercase tracking-[0.08em]";

/**
 * Bulk toggle sitting on the section-label row. Deliberately not `ITEM_CLASSES`
 * — a full-width menu row here would read as another column rather than as an
 * action on all of them.
 */
const BULK_CLASSES = `${LABEL_CLASSES} cursor-pointer rounded-md px-2 py-1 text-on-surface-variant transition-colors duration-150 hover:bg-glass hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-on-surface-variant`;

/**
 * Trigger and floating panel letting the viewer pick which columns a list table
 * shows, plus "Show all" / "Hide all" and a "Reset to default" action returning
 * to the table's declared set.
 *
 * Mounts in an `AdminPageHeader`'s `columnPicker` slot (or, where there is no
 * such header, alongside the section title), and is driven entirely by
 * `useColumnVisibility` — this component owns no visibility state of its own,
 * only the panel's open/closed state.
 *
 * The panel renders through a portal so the page's own overflow can never clip
 * it, and `useAnchoredPanel` fits it to the viewport: right-aligned to the
 * trigger since the trigger sits near the viewport's right edge, flipped above
 * it when there is no room below, and capped at the height its side offers.
 * The section label and the reset action are held at the panel's edges while
 * only the checkbox list scrolls, so the two are still reachable on a table
 * with seventeen columns. Past {@link GRID_THRESHOLD} options the panel widens
 * into a two-column grid, halving how far that list has to scroll.
 *
 * It uses the dialog a11y pattern (checkboxes rule out menu-pattern arrow-key
 * semantics) and closes on outside click or Escape. Toggling a column
 * deliberately leaves the panel open, so several columns can be adjusted in
 * one visit.
 */
export function ColumnPicker({ options, value, onChange, onReset, customized }: ColumnPickerProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const config = useMotionConfig("snappy");
  // Unique per instance: a closing panel can still be animating out while the
  // next one mounts, so a fixed id would break getElementById lookups.
  const panelId = `column-picker-${useId()}`;

  const wide = options.length > GRID_THRESHOLD;
  const coords = useAnchoredPanel({
    open,
    anchorRef: buttonRef,
    width: wide ? WIDE_WIDTH : NARROW_WIDTH,
    align: "end",
    preferredMaxHeight: MAX_PANEL_HEIGHT,
  });
  // Judged on the width actually granted, not the one asked for: a narrow
  // viewport clamps the panel, and the grid then folds back to one column.
  const twoColumn = wide && !!coords && coords.width >= GRID_MIN_WIDTH;

  const allShown = options.length > 0 && value.length === options.length;

  useDialogA11y({
    open,
    onClose: () => setOpen(false),
    anchorRef: buttonRef,
    panelId,
    ready: coords !== null,
  });

  // Slide out of the trigger, whichever side the panel ended up on.
  const offset = coords?.placement === "top" ? 6 : -6;
  const transitions = useTransition(open, {
    from: { opacity: 0, y: offset },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: offset },
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
                    bottom: coords.bottom,
                    left: coords.left,
                    width: coords.width,
                    maxHeight: coords.maxHeight,
                    display: "flex",
                    flexDirection: "column",
                    opacity: style.opacity,
                    transform: style.y.to((y) => `translateY(${y}px)`),
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay rounded-xl p-2 text-on-surface"
                >
                  <div className="flex shrink-0 items-center justify-between gap-2 pt-1 pb-1 pl-3">
                    <span className={`${LABEL_CLASSES} text-on-surface-variant`}>Columns</span>
                    <button
                      type="button"
                      disabled={options.length === 0}
                      onClick={() =>
                        onChange(allShown ? [] : options.map((option) => option.value))
                      }
                      className={BULK_CLASSES}
                    >
                      {allShown ? "Hide all" : "Show all"}
                    </button>
                  </div>
                  {/* Only the list scrolls; the label row above and the reset
                      action below stay put however many columns there are. */}
                  <div className="min-h-0 flex-1 overflow-y-auto">
                    <CheckboxGroup
                      flush
                      columns={twoColumn ? 2 : 1}
                      options={options}
                      value={value}
                      onChange={onChange}
                      emptyMessage="Every column is always shown."
                    />
                  </div>
                  <div className="my-1 h-px shrink-0 bg-glass-border" />
                  <button
                    type="button"
                    disabled={!customized}
                    onClick={onReset}
                    className={`${ITEM_CLASSES} shrink-0`}
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
