/** @module DataTable — generic admin table with resizable columns, sort, filter, and truncation tooltips. */
"use client";

import { Inbox, type LucideIcon } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FilterSpec, SortSpec } from "@/lib/api";
import { EmptyState } from "./empty-state";
import { Skeleton } from "./skeleton";
import { type FilterOption, TableHeaderMenu } from "./table-header-menu";
import { TruncatedCell } from "./truncated-cell";

/** Definition of a single table column. */
export interface ColumnDef<T> {
  /** Column heading text; also used as the column's stable key. */
  header: string;
  /** Render the cell content for a row. */
  cell: (row: T) => React.ReactNode;
  /** Extra class names applied to each body `<td>`. */
  className?: string;
  /**
   * Opt out of the default single-line truncation. Text cells are clipped to one
   * line with an overflow tooltip by default; set this on columns whose cell
   * renders interactive or multi-line content (action links, selects, chip lists)
   * so it lays out freely instead.
   */
  noTruncate?: boolean;
  /** camelCase field name enabling server-side sort on this column (requires `onSortChange`). */
  sortField?: string;
  /** camelCase field name enabling server-side filter on this column (requires `onFilterChange`). */
  filterField?: string;
  /** Filter operator sent to the API. Defaults to `like`. */
  filterOp?: string;
  /** When set, the filter renders a select of these options (use with `filterOp: "eq"`). */
  filterOptions?: FilterOption[];
  /** Optional fixed initial width in pixels; otherwise the natural width is measured. */
  width?: number;
}

/** Props for {@link DataTable}. */
interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  rows: T[];
  loading?: boolean;
  /** Number of placeholder rows to render while loading. */
  skeletonRows?: number;
  emptyMessage?: string;
  /** Accent icon shown in the empty state. Defaults to {@link Inbox}. */
  emptyIcon?: LucideIcon;
  getRowKey: (row: T) => string;
  /** Active sort directive (controlled). Omit to disable sorting. */
  sort?: SortSpec | null;
  /** Called when the user toggles a column's sort. Required to enable sort UI. */
  onSortChange?: (sort: SortSpec | null) => void;
  /** Active filter directives (controlled). Omit to disable filtering. */
  filters?: FilterSpec[];
  /** Called when the user edits a column filter. Required to enable filter UI. */
  onFilterChange?: (filters: FilterSpec[]) => void;
}

/** Per-column skeleton widths cycle through this list for a natural, uneven look. */
const SKELETON_WIDTHS = ["w-24", "w-32", "w-20", "w-28", "w-16"];

/** Absolute minimum column width, in pixels, applied when no header minimum is known. */
const MIN_WIDTH = 60;

/** Horizontal padding of a header cell (`px-5`, both sides). Mirrors the `<th>` classes. */
const TH_PADDING_X = 40;

/** Width of the resize strip overlapping the header's right edge. */
const RESIZE_HANDLE_ALLOWANCE = 2;

/**
 * Trigger chrome around the label in an interactive header: the menu trigger's
 * `px-1` padding (8px) plus the gap (6px) and the fixed `size-4` sort/menu
 * indicator slot (16px). Mirrors {@link TableHeaderMenu}'s trigger markup —
 * the two must move together.
 */
const TRIGGER_ALLOWANCE = 30;

/** Reserved filter indicator in the trigger: the 12px funnel plus its 6px gap. */
const FILTER_ALLOWANCE = 18;

/**
 * Highest width every column may take before the total exceeds `budget`.
 *
 * Water-filling: hand every column the same ceiling and lower it until the
 * widths fit. Columns already narrower than the ceiling keep what they have and
 * hand the slack to the rest, so the ceiling only ever bites the widest columns.
 *
 * @param widths Natural widths of the columns sharing the budget.
 * @param budget Total pixels the columns may occupy.
 * @returns The shared ceiling, which may be below any single natural width.
 */
function widthCeiling(widths: number[], budget: number): number {
  const ascending = [...widths].sort((a, b) => a - b);
  let remaining = budget;
  for (let i = 0; i < ascending.length; i++) {
    const ceiling = remaining / (ascending.length - i);
    if (ceiling <= ascending[i]) return ceiling;
    // This column is under the ceiling, so it keeps its width and the rest
    // divide up what it leaves behind.
    remaining -= ascending[i];
  }
  return remaining;
}

/**
 * Fit measured natural column widths into the width actually available to the table.
 *
 * Cells clip to a single line (`white-space: nowrap`), which makes a column's
 * natural width its full, unbroken text width — so the natural widths routinely
 * add up to more than the panel can show. Only the columns whose content can
 * ellipsize give ground; `noTruncate` columns (action buttons, chip lists) and
 * explicitly sized columns keep their natural width, since they have no ellipsis
 * to fall back on.
 *
 * The shrinking is capped rather than proportional: scaling every column by the
 * same factor would squeeze an already-narrow column (and its header) just to
 * spare a column with width to burn. Instead the columns share a ceiling (see
 * {@link widthCeiling}), so a column narrower than the ceiling is left alone and
 * the overlong ones absorb the whole shortfall.
 *
 * No column sits below its own `headerMin` — the measured width of its header
 * content, so a header label is never ellipsized — nor below the absolute
 * {@link MIN_WIDTH} floor. Every column without an explicit `width` is first
 * raised to its floor (a header's full-width trigger contributes nothing to
 * the browser's own natural table layout, so a column whose body content is
 * narrow can measure narrower than its own header); only then is the
 * shortfall, if any, taken from the flexible columns. When even the floors do
 * not fit, the floored widths are returned and the panel scrolls horizontally
 * rather than clipping a column out of reach.
 *
 * @param columns Column definitions, in display order.
 * @param natural Natural width in pixels per column header.
 * @param available Content width of the table's container, in pixels. `0` (not
 *   laid out yet) leaves the widths untouched.
 * @param headerMin Optional per-column minimum width in pixels, keyed by column
 *   header; {@link MIN_WIDTH} still applies where absent or smaller.
 * @returns Fitted width in pixels per column header.
 */
export function fitColumnWidths<T>(
  columns: ColumnDef<T>[],
  natural: Record<string, number>,
  available: number,
  headerMin?: Record<string, number>
): Record<string, number> {
  if (!available) return natural;

  const floorOf = (col: ColumnDef<T>) => Math.max(MIN_WIDTH, headerMin?.[col.header] ?? 0);

  const fitted = { ...natural };
  for (const col of columns) {
    if (col.width !== undefined) continue;
    fitted[col.header] = Math.max(natural[col.header] ?? 0, floorOf(col));
  }

  const total = Object.values(fitted).reduce((sum, w) => sum + w, 0);
  if (total <= available) return fitted;

  const flexible = columns.filter((col) => !col.noTruncate && col.width === undefined);
  if (flexible.length === 0) return fitted;

  const flexibleWidths = flexible.map((col) => fitted[col.header] ?? 0);
  // Whatever the columns that cannot shrink already claim is off the table.
  const budget = available - (total - flexibleWidths.reduce((sum, w) => sum + w, 0));
  const ceiling = widthCeiling(flexibleWidths, budget);

  for (const col of flexible) {
    const width = Math.min(fitted[col.header] ?? 0, ceiling);
    fitted[col.header] = Math.max(floorOf(col), Math.floor(width));
  }
  return fitted;
}

/**
 * Generic data table with configurable columns, loading state, and empty message.
 *
 * While `loading`, it renders `skeletonRows` placeholder rows that mirror the
 * column layout (instead of a single spinner) so the header and column widths
 * stay fixed and the swap-in of real data causes no layout jump. The wrapper
 * exposes `role="status"` during loading for assistive technologies.
 *
 * Header and body cells are separated by vertical dividers, and body rows are
 * zebra-striped, so columns and rows stay visually distinct against the glass
 * surface. When `onSortChange`/`onFilterChange` are provided, a column with
 * `sortField`/`filterField` renders its whole header as a single
 * {@link TableHeaderMenu} trigger opening labeled sort actions and the column
 * filter, with persistent sort/filter indicators on the header itself. By
 * default every cell clips to a single line and reveals its full text in a
 * tooltip on overflow; columns that render interactive or multi-line content
 * opt out with `noTruncate`.
 *
 * Column widths are measured from the natural layout once real rows arrive, then
 * passed through {@link fitColumnWidths} so the whole table — including the
 * trailing actions column — stays inside the panel, and refitted whenever the
 * panel resizes. Each column's floor is its own header content width (measured
 * from a hidden nowrap sizer at the same time as the natural widths), so header
 * labels are never ellipsized by the auto-fit — or by dragging, since the same
 * floor caps the resize handles. Columns are resizable by dragging the handle on
 * each header's right edge; doing so hands the widths to the user and stops the
 * automatic refit. The panel scrolls horizontally only when the columns
 * genuinely cannot fit, so content is never clipped out of reach. Widths are
 * held in component state and are not persisted.
 */
export function DataTable<T>({
  columns,
  rows,
  loading = false,
  skeletonRows = 5,
  emptyMessage = "No data.",
  emptyIcon = Inbox,
  getRowKey,
  sort = null,
  onSortChange,
  filters,
  onFilterChange,
}: DataTableProps<T>) {
  const colSpan = columns.length;

  // Column widths in px, keyed by header. `null` until measured, so the table
  // first lays out naturally; we then fit those widths to the panel and freeze
  // them for resizing.
  const [widths, setWidths] = useState<Record<string, number> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const thRefs = useRef(new Map<string, HTMLTableCellElement>());
  // Hidden nowrap copies of each header's label, measured for the per-column
  // width floor that keeps header text from ellipsizing.
  const sizerRefs = useRef(new Map<string, HTMLElement>());
  // Natural (unfitted) widths, kept so a refit rescales from the original
  // measurement instead of ratcheting down from the already-shrunk widths.
  const naturalRef = useRef<Record<string, number> | null>(null);
  // Per-column width floors derived from the header content, applied by every
  // fit and by drag-resizing.
  const headerMinRef = useRef<Record<string, number> | null>(null);
  // Once the user drags a handle the widths are theirs — stop auto-refitting.
  const manualRef = useRef(false);
  // Latest columns, so the resize observer never has to re-subscribe: pages
  // rebuild their column array inline on every render.
  const columnsRef = useRef(columns);
  columnsRef.current = columns;
  const columnsKey = columns.map((c) => c.header).join(" ");

  // Reset measurements whenever the set of columns changes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: columnsKey captures the relevant change
  useEffect(() => {
    naturalRef.current = null;
    headerMinRef.current = null;
    manualRef.current = false;
    setWidths(null);
  }, [columnsKey]);

  // Measure natural column widths once real rows have painted, then fit them to
  // the panel. Header-only widths (while loading, or an empty table rendering a
  // single colSpan cell) are not representative, so wait for rows. The header
  // sizers are measured in the same pass: the table is not yet `table-fixed`,
  // so nothing is clamped and each sizer reports the label's full text width.
  useEffect(() => {
    if (widths || loading || rows.length === 0) return;
    const measured: Record<string, number> = {};
    const headerMin: Record<string, number> = {};
    for (const col of columns) {
      const el = thRefs.current.get(col.header);
      if (el) measured[col.header] = col.width ?? el.offsetWidth;
      const sortable = !!col.sortField && !!onSortChange;
      const filterable = !!col.filterField && !!onFilterChange;
      let min =
        Math.ceil(sizerRefs.current.get(col.header)?.offsetWidth ?? 0) +
        TH_PADDING_X +
        RESIZE_HANDLE_ALLOWANCE;
      if (sortable || filterable) min += TRIGGER_ALLOWANCE;
      if (filterable) min += FILTER_ALLOWANCE;
      headerMin[col.header] = min;
    }
    if (Object.keys(measured).length !== columns.length) return;
    naturalRef.current = measured;
    headerMinRef.current = headerMin;
    setWidths(fitColumnWidths(columns, measured, wrapperRef.current?.clientWidth ?? 0, headerMin));
  }, [columns, widths, loading, rows.length, onSortChange, onFilterChange]);

  // Refit when the panel resizes (window, sidebar) so the columns give ground
  // instead of the rightmost one falling off the edge.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const natural = naturalRef.current;
      if (!natural || manualRef.current) return;
      setWidths(
        fitColumnWidths(
          columnsRef.current,
          natural,
          el.clientWidth,
          headerMinRef.current ?? undefined
        )
      );
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const startResize = useCallback((header: string, e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    manualRef.current = true;
    const startX = e.clientX;
    const startW = thRefs.current.get(header)?.offsetWidth ?? MIN_WIDTH;
    // Dragging obeys the same header floor as the fit, so a header can never
    // be squeezed into ellipsis by hand either.
    const floor = Math.max(MIN_WIDTH, headerMinRef.current?.[header] ?? 0);
    const onMove = (ev: PointerEvent) => {
      const next = Math.max(floor, startW + (ev.clientX - startX));
      setWidths((w) => ({ ...(w ?? {}), [header]: next }));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  /** Set or clear a column's sort from the header menu's explicit direction. */
  const setColumnSort = useCallback(
    (field: string, direction: "asc" | "desc" | null) => {
      if (!onSortChange) return;
      onSortChange(direction ? { field, descending: direction === "desc" } : null);
    },
    [onSortChange]
  );

  /** Replace (or clear) the filter for a single field and emit the new set. */
  const setColumnFilter = useCallback(
    (field: string, op: string, value: string) => {
      if (!onFilterChange) return;
      const others = (filters ?? []).filter((f) => f.field !== field);
      onFilterChange(value ? [...others, { field, op, value }] : others);
    },
    [onFilterChange, filters]
  );

  return (
    <div
      ref={wrapperRef}
      className="overflow-x-auto rounded-2xl glass-panel"
      {...(loading ? { role: "status", "aria-busy": true, "aria-label": "Loading" } : {})}
    >
      <table className={`w-full border-collapse text-sm ${widths ? "table-fixed" : ""}`}>
        <colgroup>
          {columns.map((col) => (
            <col
              key={col.header}
              style={widths ? { width: `${widths[col.header]}px` } : undefined}
            />
          ))}
        </colgroup>
        <thead className="bg-glass-strong/70 backdrop-blur-md">
          <tr>
            {columns.map((col) => {
              const sortable = !!col.sortField && !!onSortChange;
              const filterable = !!col.filterField && !!onFilterChange;
              const direction =
                col.sortField && sort?.field === col.sortField
                  ? sort.descending
                    ? "desc"
                    : "asc"
                  : null;
              return (
                <th
                  key={col.header}
                  ref={(el) => {
                    if (el) thRefs.current.set(col.header, el);
                    else thRefs.current.delete(col.header);
                  }}
                  className="relative border-divider border-b px-5 py-3 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant [&:not(:last-child)]:border-r"
                >
                  {sortable || filterable ? (
                    <TableHeaderMenu
                      label={col.header}
                      sortDirection={sortable ? direction : undefined}
                      onSortChange={
                        sortable ? (dir) => setColumnSort(col.sortField as string, dir) : undefined
                      }
                      filterValue={
                        filterable
                          ? (filters?.find((f) => f.field === col.filterField)?.value ?? "")
                          : undefined
                      }
                      onFilterChange={
                        filterable
                          ? (v) =>
                              setColumnFilter(col.filterField as string, col.filterOp ?? "like", v)
                          : undefined
                      }
                      filterOptions={col.filterOptions}
                    />
                  ) : (
                    <span className="block truncate">{col.header}</span>
                  )}
                  {/* The label is painted via ::before so it exists for width
                      measurement without duplicating the header text in the
                      document (text queries and copy-paste see it once). */}
                  <span
                    aria-hidden="true"
                    data-header-sizer="true"
                    data-label={col.header}
                    ref={(el) => {
                      if (el) sizerRefs.current.set(col.header, el);
                      else sizerRefs.current.delete(col.header);
                    }}
                    className="pointer-events-none invisible absolute top-0 left-0 inline-block whitespace-nowrap before:content-[attr(data-label)]"
                  />
                  <span
                    aria-hidden="true"
                    data-resize-handle="true"
                    onPointerDown={(e) => startResize(col.header, e)}
                    className="absolute top-0 right-0 z-10 h-full w-2 cursor-col-resize touch-none select-none transition-colors hover:bg-accent/30"
                  />
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: skeletonRows }, (_, rowIndex) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
              <tr key={rowIndex} className="border-divider/60 border-t">
                {columns.map((col, colIndex) => (
                  <td
                    key={col.header}
                    className="border-divider/60 px-5 py-3 [&:not(:last-child)]:border-r"
                  >
                    <Skeleton
                      className={`h-4 ${SKELETON_WIDTHS[colIndex % SKELETON_WIDTHS.length]}`}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className="px-5 py-10 text-on-surface-variant">
                <EmptyState
                  icon={emptyIcon}
                  animation="spin-occasional"
                  description={emptyMessage}
                />
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className="border-divider/60 border-t text-on-surface transition-colors even:bg-glass-strong/15 hover:bg-accent-soft/40"
              >
                {columns.map((col) => (
                  <td
                    key={col.header}
                    className={[
                      "overflow-hidden border-glass-border/40 px-5 py-3 [&:not(:last-child)]:border-r",
                      col.className,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {col.noTruncate ? (
                      col.cell(row)
                    ) : (
                      <TruncatedCell>{col.cell(row)}</TruncatedCell>
                    )}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
