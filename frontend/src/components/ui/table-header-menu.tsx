/** @module TableHeaderMenu — unified column header: a full-width trigger opening a menu with labeled sort actions and the column filter. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { ArrowDown, ArrowUp, ChevronDown, Funnel } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";
import { Input } from "./input";
import { Select } from "./select";

/** A choice rendered in the filter's select variant. */
export interface FilterOption {
  /** Visible label. */
  label: string;
  /** Value submitted to {@link TableHeaderMenuProps.onFilterChange}. */
  value: string;
}

/** Props for {@link TableHeaderMenu}. */
interface TableHeaderMenuProps {
  /** Column header text; the trigger's visible label and the menu's accessible name. */
  label: string;
  /** Active sort direction on this column, or `null`. Omit when the column is not sortable. */
  sortDirection?: "asc" | "desc" | null;
  /** Sets or clears the column sort. Present iff the column is sortable. */
  onSortChange?: (direction: "asc" | "desc" | null) => void;
  /** Current filter value; empty string means no filter. Omit when the column is not filterable. */
  filterValue?: string;
  /** Called with the new filter value (debounced for the text variant). Present iff filterable. */
  onFilterChange?: (value: string) => void;
  /** When provided, the filter section renders a select of these options instead of a free-text input. */
  filterOptions?: FilterOption[];
}

const PANEL_WIDTH = 220;
const GAP = 6;
const EDGE_PADDING = 8;
const DEBOUNCE_MS = 300;

interface Coords {
  top: number;
  left: number;
}

/** Menu action row styling, mirroring the app's dropdown menu items (see UserMenu). */
const ITEM_CLASSES =
  "flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50";

/**
 * Unified header control for a sortable and/or filterable table column: the
 * whole header is one full-width button that opens a floating glass menu with
 * labeled "Sort ascending" / "Sort descending" actions and, below a divider,
 * the column filter (a debounced text input or, when `options` are given, a
 * select). The trigger carries persistent state indicators — an accent
 * arrow for the active sort direction, an accent funnel + dot when a filter
 * is applied, and a subtle chevron (strengthening on hover) when idle.
 *
 * The panel renders through a portal so it is never clipped by the table's
 * overflow, uses the dialog a11y pattern (it embeds an input, which rules out
 * menu-pattern arrow-key semantics), and closes on outside click or Escape.
 * Choosing a sort closes the menu; editing the filter keeps it open so the
 * value can be refined.
 */
export function TableHeaderMenu({
  label,
  sortDirection,
  onSortChange,
  filterValue,
  onFilterChange,
  filterOptions,
}: TableHeaderMenuProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [draft, setDraft] = useState(filterValue ?? "");
  const config = useMotionConfig("snappy");
  // Unique per instance: two header menus can coexist in the DOM while one is
  // still animating out, so a fixed id would break getElementById lookups.
  const panelId = `table-header-menu-${useId()}`;

  const sortable = sortDirection !== undefined && !!onSortChange;
  const filterable = filterValue !== undefined && !!onFilterChange;
  const filterActive = (filterValue ?? "") !== "";

  // Keep the draft in sync when the applied value changes from outside.
  useEffect(() => {
    setDraft(filterValue ?? "");
  }, [filterValue]);

  const computeCoords = useCallback((): Coords | null => {
    const anchor = buttonRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.left, window.innerWidth - PANEL_WIDTH - EDGE_PADDING)
    );
    return { top: rect.bottom + GAP, left };
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

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  /** Update the text draft and debounce the committed value. */
  const onText = useCallback(
    (next: string) => {
      setDraft(next);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onFilterChange?.(next), DEBOUNCE_MS);
    },
    [onFilterChange]
  );

  /** Apply a sort direction, toggling it off when it is already active, and close the menu. */
  const chooseSort = useCallback(
    (direction: "asc" | "desc") => {
      onSortChange?.(sortDirection === direction ? null : direction);
      setOpen(false);
    },
    [onSortChange, sortDirection]
  );

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`group flex w-full min-w-0 cursor-pointer items-center gap-1.5 rounded-md px-1 py-0.5 text-left uppercase tracking-[0.08em] transition-colors hover:bg-accent-soft/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 ${sortDirection ? "text-accent" : "hover:text-on-surface"}`}
      >
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {filterable ? (
          // Rendered even when idle (just invisible) so the header's measured
          // minimum width stays valid and the label never shifts when a
          // filter is applied.
          <span
            aria-hidden="true"
            data-filter-indicator={filterActive ? "active" : "idle"}
            className={`relative shrink-0 transition-opacity ${filterActive ? "opacity-100" : "opacity-0"}`}
          >
            <Funnel size={12} strokeWidth={1.8} className="text-accent" />
            <span className="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-accent" />
          </span>
        ) : null}
        <span
          aria-hidden="true"
          className="inline-flex size-4 shrink-0 items-center justify-center"
        >
          {sortDirection === "asc" ? (
            <ArrowUp size={16} strokeWidth={1.8} className="text-accent" />
          ) : sortDirection === "desc" ? (
            <ArrowDown size={16} strokeWidth={1.8} className="text-accent" />
          ) : (
            <ChevronDown
              size={16}
              strokeWidth={1.8}
              className="text-on-surface-variant/40 transition-colors group-hover:text-on-surface-variant"
            />
          )}
        </span>
      </button>
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
                  aria-label={`${label} column menu`}
                  style={{
                    position: "fixed",
                    top: coords.top,
                    left: coords.left,
                    width: PANEL_WIDTH,
                    opacity: style.opacity,
                    transform: style.y.to((y) => `translateY(${y}px)`),
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay rounded-xl p-2 text-on-surface"
                >
                  {sortable ? (
                    <>
                      <button
                        type="button"
                        aria-pressed={sortDirection === "asc"}
                        onClick={() => chooseSort("asc")}
                        className={`${ITEM_CLASSES} ${sortDirection === "asc" ? "bg-accent-soft/40 text-accent" : ""}`}
                      >
                        <ArrowUp size={16} strokeWidth={1.8} aria-hidden="true" />
                        Sort ascending
                      </button>
                      <button
                        type="button"
                        aria-pressed={sortDirection === "desc"}
                        onClick={() => chooseSort("desc")}
                        className={`${ITEM_CLASSES} ${sortDirection === "desc" ? "bg-accent-soft/40 text-accent" : ""}`}
                      >
                        <ArrowDown size={16} strokeWidth={1.8} aria-hidden="true" />
                        Sort descending
                      </button>
                    </>
                  ) : null}
                  {sortable && filterable ? <div className="my-1 h-px bg-glass-border" /> : null}
                  {filterable ? (
                    <div>
                      <div className="px-3 pt-1 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-on-surface-variant">
                        Filter
                      </div>
                      {filterOptions ? (
                        <Select
                          value={filterValue ?? ""}
                          onChange={(e) => onFilterChange?.(e.target.value)}
                        >
                          <option value="">All</option>
                          {filterOptions.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          type="text"
                          placeholder={`Filter ${label}…`}
                          value={draft}
                          onChange={(e) => onText(e.target.value)}
                        />
                      )}
                    </div>
                  ) : null}
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
