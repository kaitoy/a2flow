import type React from "react";
import { Skeleton } from "./skeleton";

export interface ColumnDef<T> {
  header: string;
  cell: (row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  rows: T[];
  loading?: boolean;
  /** Number of placeholder rows to render while loading. */
  skeletonRows?: number;
  emptyMessage?: string;
  getRowKey: (row: T) => string;
}

/** Per-column skeleton widths cycle through this list for a natural, uneven look. */
const SKELETON_WIDTHS = ["w-24", "w-32", "w-20", "w-28", "w-16"];

/**
 * Generic data table with configurable columns, loading state, and empty message.
 *
 * While `loading`, it renders `skeletonRows` placeholder rows that mirror the
 * column layout (instead of a single spinner) so the header and column widths
 * stay fixed and the swap-in of real data causes no layout jump. The wrapper
 * exposes `role="status"` during loading for assistive technologies.
 */
export function DataTable<T>({
  columns,
  rows,
  loading = false,
  skeletonRows = 5,
  emptyMessage = "No data.",
  getRowKey,
}: DataTableProps<T>) {
  const colSpan = columns.length;

  return (
    <div
      className="overflow-hidden rounded-2xl glass-panel"
      {...(loading ? { role: "status", "aria-busy": true, "aria-label": "Loading" } : {})}
    >
      <table className="w-full text-sm">
        <thead className="bg-glass-strong/40 backdrop-blur-md">
          <tr>
            {columns.map((col) => (
              <th
                key={col.header}
                className="px-5 py-3 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: skeletonRows }, (_, rowIndex) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
              <tr key={rowIndex} className="border-t border-glass-border">
                {columns.map((col, colIndex) => (
                  <td key={col.header} className="px-5 py-3">
                    <Skeleton
                      className={`h-4 ${SKELETON_WIDTHS[colIndex % SKELETON_WIDTHS.length]}`}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className="px-5 py-6 text-on-surface-variant">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className="border-t border-glass-border text-on-surface transition-colors hover:bg-accent-soft/40"
              >
                {columns.map((col) => (
                  <td
                    key={col.header}
                    className={["px-5 py-3", col.className].filter(Boolean).join(" ")}
                  >
                    {col.cell(row)}
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
