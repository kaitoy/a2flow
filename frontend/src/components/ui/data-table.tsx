/** @module DataTable — generic admin table with resizable columns, sort, filter, and truncation tooltips. */
"use client";

import { Inbox, type LucideIcon } from "lucide-react";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FilterSpec, SortSpec } from "@/lib/api";
import type { CheckboxOption } from "./checkbox-group";
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
  /**
   * Marks the column as filtered by tag rather than by a field of the record.
   *
   * Tags are a separate axis from `filters`: they are not a column of any
   * resource, so the API takes them as their own repeatable parameter. Such a
   * column reads its state from {@link DataTableProps.tagIds} and writes it
   * through {@link DataTableProps.onTagIdsChange}, and offers a multi-select
   * whose selections are ANDed. It has no `filterField` and cannot be sorted.
   */
  filterKind?: "tags";
  /** Tag options offered by a `filterKind: "tags"` column, with their palette swatches. */
  tagOptions?: CheckboxOption[];
  /** Optional fixed initial width in pixels; otherwise the natural width is measured. */
  width?: number;
  /**
   * How the column participates in the column picker (see `useColumnVisibility`).
   *
   * - `"always"` — not offered in the picker and always rendered. Use for the
   *   identifier column linking to the detail page, the actions column, and any
   *   column whose `header` is empty (there would be nothing to label it with).
   * - `"default"` — offered in the picker and shown unless the viewer turns it
   *   off. The default when unset.
   * - `"optional"` — offered in the picker but hidden until the viewer turns it on.
   */
  visibility?: "always" | "default" | "optional";
}

/**
 * Shared `filterOptions` for a boolean column filtered with `filterOp: "eq"` —
 * renders an "All / Yes / No" select in the column header menu. The values are
 * the strings the list API expects for `field:eq:true` / `field:eq:false`.
 */
export const BOOL_FILTER_OPTIONS: FilterOption[] = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
];

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
  /** Tag ids the list is narrowed by (controlled). Omit to disable the tag filter UI. */
  tagIds?: string[];
  /** Called when the user changes the tag selection. Required to enable the tag filter UI. */
  onTagIdsChange?: (tagIds: string[]) => void;
  /**
   * `getRowKey` value of the row to call out, e.g. the task a hovered dependency
   * chip points at. No row is highlighted when null or omitted.
   */
  highlightedRowKey?: string | null;
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
 * `pl-1` + `pr-2.5` padding, and nothing else. Its sort/filter indicator is
 * absolutely positioned in the header cell's right padding (see
 * {@link TableHeaderMenu}), so the glyph itself costs the column nothing —
 * which is the whole reason a menu column is barely wider than a plain one.
 * The right side is the larger half because the slot reaches back over it to
 * stay clear of the resize strip. Mirrors the trigger's markup; the two must
 * move together.
 */
const TRIGGER_ALLOWANCE = 14;

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

/** Which header controls a column offers. See {@link headerControls}. */
interface HeaderControls {
  /** The header offers sort actions. */
  sortable: boolean;
  /** The header filters by tag rather than by a field of the record. */
  tagFilterable: boolean;
  /** The header offers a filter of either kind. */
  filterable: boolean;
  /** The header renders a {@link TableHeaderMenu} rather than plain text. */
  interactive: boolean;
}

/**
 * Resolve a column's header controls from the handlers the table was given.
 *
 * Both the width measurement and the header markup ask this one function, so
 * the trigger allowance added to a column's floor cannot drift from what is
 * actually rendered — it already had: the measurement recognised only
 * `sortField`/`filterField` columns and so gave no allowance to a
 * `filterKind: "tags"` column, which has neither yet still renders the menu.
 *
 * @param col The column definition.
 * @param onSortChange The table's sort handler, if sorting is enabled.
 * @param onFilterChange The table's filter handler, if filtering is enabled.
 * @param onTagIdsChange The table's tag handler, if the tag filter is enabled.
 * @returns The controls that column's header renders.
 */
function headerControls<T>(
  col: ColumnDef<T>,
  onSortChange?: DataTableProps<T>["onSortChange"],
  onFilterChange?: DataTableProps<T>["onFilterChange"],
  onTagIdsChange?: DataTableProps<T>["onTagIdsChange"]
): HeaderControls {
  const sortable = !!col.sortField && !!onSortChange;
  const tagFilterable = col.filterKind === "tags" && !!onTagIdsChange;
  const filterable = (!!col.filterField && !!onFilterChange) || tagFilterable;
  return { sortable, tagFilterable, filterable, interactive: sortable || filterable };
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
 * filter, with a persistent sort/filter indicator on the header itself — one
 * slot, parked in the header cell's padding, so an interactive column is no
 * wider than a plain one. By
 * default every cell clips to a single line and reveals its full text in a
 * tooltip on overflow; columns that render interactive or multi-line content
 * opt out with `noTruncate`.
 *
 * A caller can call one row out with `highlightedRowKey` — used to answer "which
 * row is this reference pointing at?" when a cell names another row (a hovered
 * dependency chip). Every row also carries its key as `data-row-key`, which is
 * how such a caller, or a test, finds the row in the DOM.
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
 *
 * `columns` is the set actually on screen: callers that let the viewer choose
 * which columns to show (see `useColumnVisibility`) pass the filtered list, and
 * the table treats it as a fresh layout — measurements are re-taken and any
 * hand-dragged widths are released, since the columns sharing the panel have
 * changed. A sort or filter left pointing at a column that is no longer in
 * `columns` is dropped through `onSortChange`/`onFilterChange`, so the rows on
 * screen are never ordered or narrowed by an invisible criterion.
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
  tagIds,
  onTagIdsChange,
  highlightedRowKey = null,
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

  // Drop any sort or filter aimed at a column that is no longer on screen.
  // Hiding a column through the column picker would otherwise leave the list
  // ordered — or, worse, narrowed — by a criterion with nothing on the page to
  // reveal or undo it: rows are missing and the table looks broken. The
  // directives are only emitted from a visible header's menu, so a change of
  // columns is the only thing that can strand one.
  // biome-ignore lint/correctness/useExhaustiveDependencies: columnsKey captures the relevant change
  useEffect(() => {
    const current = columnsRef.current;
    if (onSortChange && sort && !current.some((col) => col.sortField === sort.field)) {
      onSortChange(null);
    }
    if (onFilterChange && filters?.length) {
      const kept = filters.filter((f) => current.some((col) => col.filterField === f.field));
      if (kept.length !== filters.length) onFilterChange(kept);
    }
    // Tags live outside `filters`, so the sweep above cannot reach them; clear
    // them here for the same reason it clears the rest.
    if (onTagIdsChange && tagIds?.length && !current.some((col) => col.filterKind === "tags")) {
      onTagIdsChange([]);
    }
  }, [columnsKey, sort, filters, onSortChange, onFilterChange, tagIds, onTagIdsChange]);

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
      const { interactive } = headerControls(col, onSortChange, onFilterChange, onTagIdsChange);
      headerMin[col.header] =
        Math.ceil(sizerRefs.current.get(col.header)?.offsetWidth ?? 0) +
        TH_PADDING_X +
        RESIZE_HANDLE_ALLOWANCE +
        (interactive ? TRIGGER_ALLOWANCE : 0);
    }
    if (Object.keys(measured).length !== columns.length) return;
    naturalRef.current = measured;
    headerMinRef.current = headerMin;
    setWidths(fitColumnWidths(columns, measured, wrapperRef.current?.clientWidth ?? 0, headerMin));
  }, [columns, widths, loading, rows.length, onSortChange, onFilterChange, onTagIdsChange]);

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
              const { sortable, tagFilterable, filterable, interactive } = headerControls(
                col,
                onSortChange,
                onFilterChange,
                onTagIdsChange
              );
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
                  {interactive ? (
                    <TableHeaderMenu
                      label={col.header}
                      sortDirection={sortable ? direction : undefined}
                      onSortChange={
                        sortable ? (dir) => setColumnSort(col.sortField as string, dir) : undefined
                      }
                      filterValue={
                        filterable && !tagFilterable
                          ? (filters?.find((f) => f.field === col.filterField)?.value ?? "")
                          : undefined
                      }
                      onFilterChange={
                        filterable && !tagFilterable
                          ? (v) =>
                              setColumnFilter(col.filterField as string, col.filterOp ?? "like", v)
                          : undefined
                      }
                      filterOptions={tagFilterable ? undefined : col.filterOptions}
                      filterValues={tagFilterable ? (tagIds ?? []) : undefined}
                      onFilterValuesChange={tagFilterable ? onTagIdsChange : undefined}
                      filterCheckboxOptions={tagFilterable ? col.tagOptions : undefined}
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
                data-row-key={getRowKey(row)}
                className={[
                  "border-divider/60 border-t text-on-surface transition-colors even:bg-glass-strong/15 hover:bg-accent-soft/40",
                  // The zebra stripe is a `:nth-child(even)` rule, so it outranks a
                  // plain background utility — the highlight fill has to be forced.
                  highlightedRowKey === getRowKey(row)
                    ? "bg-accent-soft/40! ring-2 ring-inset ring-accent/50"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
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
