import { Skeleton } from "@/components/ui/skeleton";

/**
 * Placeholder message list + input bar shown while a chat panel is loading.
 * Mirrors {@link MessageList}'s container classes (`flex-1 overflow-y-auto
 * px-4 py-6` / `mx-auto flex max-w-3xl flex-col`) so it swaps in without a
 * jump. Renders no outer landmark of its own — callers wrap it in their own
 * `role="status"` container (e.g. the chat route's `loading.tsx`, or
 * {@link WorkflowSessionSkeleton}, which composes it alongside its own
 * chrome).
 */
export function ChatPanelSkeleton() {
  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col">
          <Skeleton className="ml-auto mb-3 h-16 w-2/3 rounded-2xl rounded-tr-md" />
          <Skeleton className="mb-3 h-24 w-3/4 rounded-2xl rounded-tl-md" />
          <Skeleton className="ml-auto mb-3 h-12 w-1/2 rounded-2xl rounded-tr-md" />
          <Skeleton className="mb-3 h-20 w-2/3 rounded-2xl rounded-tl-md" />
        </div>
      </div>
      <div className="shrink-0 px-4 pb-6 pt-2">
        <Skeleton className="mx-auto h-14 w-full max-w-3xl rounded-2xl" />
      </div>
    </>
  );
}
