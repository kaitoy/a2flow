/** @module DashboardSkeleton — Placeholder for the dashboard's tiles and panels. */
"use client";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * The dashboard's body before its first reading arrives: five tiles over two
 * rows of panels, in the same grid the real ones take. Shared by the route's
 * `loading.tsx` and the page's own first-load state so the two are identical.
 * Render it inside a `ConsoleFrame`.
 */
export function DashboardSkeleton() {
  return (
    <>
      <div className="flex flex-wrap gap-4 *:min-w-36 *:flex-1 *:basis-36">
        {["a", "b", "c", "d", "e"].map((key) => (
          <div key={key} className="console-panel flex flex-col gap-3 p-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-12 w-20" />
            <Skeleton className="h-3 w-28" />
          </div>
        ))}
      </div>
      {["f", "g"].map((row) => (
        <div key={row} className="grid gap-4 @4xl:grid-cols-3">
          <div className="console-panel flex flex-col gap-4 p-5 @4xl:col-span-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-48 w-full rounded-lg" />
          </div>
          <div className="console-panel flex flex-col gap-4 p-5">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-48 w-full rounded-lg" />
          </div>
        </div>
      ))}
    </>
  );
}
