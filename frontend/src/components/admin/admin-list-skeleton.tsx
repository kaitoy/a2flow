import { Skeleton } from "@/components/ui/skeleton";

/** Per-column skeleton widths cycle through this list, matching {@link DataTable}'s own loading rows. */
const SKELETON_WIDTHS = ["w-24", "w-32", "w-20", "w-28", "w-16"];

/**
 * Placeholder table shown in an admin list route's `loading.tsx`, before
 * {@link DataTable} itself has mounted. Mirrors `DataTable`'s loading-row
 * markup (`glass-panel` wrapper, `bg-glass-strong/70` header, shimmering
 * `SKELETON_WIDTHS`-cycled cells) but with plain-text headers — no sort,
 * filter, or resize affordances, since those depend on interaction state the
 * real table owns.
 *
 * @param columns - Header labels, in display order.
 * @param rows - Number of placeholder rows to render. Defaults to 5.
 */
export function AdminListSkeleton({ columns, rows = 5 }: { columns: string[]; rows?: number }) {
  return (
    <div
      className="overflow-hidden rounded-2xl glass-panel"
      role="status"
      aria-busy="true"
      aria-label="Loading"
    >
      <table className="w-full border-collapse text-sm">
        <thead className="bg-glass-strong/70 backdrop-blur-md">
          <tr>
            {columns.map((header) => (
              <th
                key={header}
                className="border-divider border-b px-5 py-3 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-on-surface-variant [&:not(:last-child)]:border-r"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, rowIndex) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
            <tr key={rowIndex} className="border-divider/60 border-t">
              {columns.map((header, colIndex) => (
                <td
                  key={header}
                  className="border-divider/60 px-5 py-3 [&:not(:last-child)]:border-r"
                >
                  <Skeleton
                    className={`h-4 ${SKELETON_WIDTHS[colIndex % SKELETON_WIDTHS.length]}`}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
