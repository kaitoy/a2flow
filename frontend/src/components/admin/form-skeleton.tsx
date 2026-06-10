import { Skeleton } from "@/components/ui/skeleton";

/**
 * Placeholder for an admin edit/detail form while its record loads.
 *
 * Mirrors the shared form shell — a `glass-panel-strong` card holding a stack
 * of label + input rows and a trailing button row — so the layout stays fixed
 * and the real form swaps in without a jump. Exposes `role="status"` for
 * assistive technologies.
 *
 * @param fields - Number of label/input placeholder rows to render.
 */
export function FormSkeleton({ fields }: { fields: number }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
    >
      {Array.from({ length: fields }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
        <div key={i} className="flex flex-col gap-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-11 w-full rounded-xl" />
        </div>
      ))}
      <div className="flex gap-2">
        <Skeleton className="h-11 w-20 rounded-xl" />
        <Skeleton className="h-11 w-24 rounded-xl" />
      </div>
    </div>
  );
}
