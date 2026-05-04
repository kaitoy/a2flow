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

export function DataTable<T>({
  columns,
  rows,
  loading = false,
  emptyMessage = "No data.",
  getRowKey,
}: DataTableProps<T>) {
  const colSpan = columns.length;

  return (
    <div className="overflow-hidden rounded border border-outline-variant">
      <table className="w-full text-sm">
        <thead className="bg-surface-container-highest">
          <tr>
            {columns.map((col) => (
              <th
                key={col.header}
                className="px-4 py-2 text-left text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={colSpan} className="px-4 py-4 text-on-surface-variant">
                Loading…
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className="px-4 py-4 text-on-surface-variant">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={getRowKey(row)} className="border-t border-outline-variant text-on-surface">
                {columns.map((col) => (
                  <td
                    key={col.header}
                    className={["px-4 py-2", col.className].filter(Boolean).join(" ")}
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
