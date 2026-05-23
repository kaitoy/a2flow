import type React from "react";

export interface ColumnDef<T> {
  header: string;
  cell: (row: T) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  rows: T[];
  loading?: boolean;
  emptyMessage?: string;
  getRowKey: (row: T) => string;
}

/** Generic data table with configurable columns, loading state, and empty message. */
export function DataTable<T>({
  columns,
  rows,
  loading = false,
  emptyMessage = "No data.",
  getRowKey,
}: DataTableProps<T>) {
  const colSpan = columns.length;

  return (
    <div className="overflow-hidden rounded-2xl glass-panel">
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
            <tr>
              <td colSpan={colSpan} className="px-5 py-6 text-on-surface-variant">
                Loading…
              </td>
            </tr>
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
