import { AppHeader } from "@/components/AppHeader";
import { ChatPanelSkeleton } from "@/components/ChatPanelSkeleton";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TASK_TIMELINE_ASIDE_CLASS,
  TASK_TIMELINE_HEADER_CLASS,
  TASK_TIMELINE_LIST_CLASS,
} from "@/components/WorkflowTaskTimeline";

/**
 * Placeholder chat layout shown while a WorkflowSession record loads, so the
 * page presents the header shell and a few message-bubble skeletons instead of
 * flashing a blank screen. Shares its sidebar chrome classes with
 * {@link WorkflowTaskTimeline} so this loading state can't silently drift from
 * the real layout it stands in for. Used both by the workflow session page's
 * own post-mount loading branch and by that route's `loading.tsx`.
 */
export function WorkflowSessionSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="flex h-dvh overflow-hidden">
      <div className={TASK_TIMELINE_ASIDE_CLASS}>
        <div className={TASK_TIMELINE_HEADER_CLASS}>
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-4 rounded" />
        </div>
        <div className={TASK_TIMELINE_LIST_CLASS}>
          <div className="flex items-start gap-2.5 px-2 py-2">
            <Skeleton className="size-5 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-full rounded" />
          </div>
          <div className="flex items-start gap-2.5 px-2 py-2">
            <Skeleton className="size-5 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-full rounded" />
          </div>
          <div className="flex items-start gap-2.5 px-2 py-2">
            <Skeleton className="size-5 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-full rounded" />
          </div>
        </div>
      </div>
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader>
          <span className="h-6 w-px shrink-0 bg-glass-border" aria-hidden="true" />
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-accent shadow-glow animate-pulse" />
          <Skeleton className="h-5 w-40" />
        </AppHeader>

        <ChatPanelSkeleton />
      </div>
    </div>
  );
}
