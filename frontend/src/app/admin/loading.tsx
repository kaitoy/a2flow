import { Skeleton } from "@/components/ui/skeleton";

/** Number of quick-action cards on the welcome page: "Start chat" plus each `adminNavItems` entry. */
const CARD_COUNT = 7;

/** Route loading fallback for the `/admin` welcome page, mirroring its title/subtitle + quick-action card grid. */
export default function Loading() {
  return (
    <div role="status" aria-label="Loading" className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8">
        <Skeleton className="h-8 w-64 rounded" />
        <Skeleton className="mt-3 h-4 w-96 rounded" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: CARD_COUNT }, (_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
          <div key={i} className="flex items-start gap-4 rounded-2xl glass-panel p-5">
            <Skeleton className="h-11 w-11 shrink-0 rounded-xl" />
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <Skeleton className="h-4 w-24 rounded" />
              <Skeleton className="h-3 w-full rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
