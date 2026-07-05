import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

/** Props for {@link RouteErrorFallback}. */
export interface RouteErrorFallbackProps {
  /** Re-render the segment, per Next.js's `error.tsx` `reset` callback. */
  reset: () => void;
  /** Headline shown above the description. Defaults to "Something went wrong". */
  title?: string;
  /** Supporting line beneath the title. */
  description?: string;
  /** When set alongside {@link homeLabel}, renders a secondary link button. */
  homeHref?: string;
  /** Label for the {@link homeHref} link button. */
  homeLabel?: string;
  /** `"screen"` fills the viewport (no persistent chrome above/around it); `"full"` fills its parent (a shell's content area stays mounted around it). */
  fill: "screen" | "full";
}

/**
 * Shared fallback body for every route-level `error.tsx` boundary. Mirrors the
 * existing `WorkflowSessionLoadError` pattern (same icon, animation, and
 * `EmptyState` + `Button` shape) so a render-time crash reads as consistent
 * with the app's existing load-failure UI rather than a different style.
 */
export function RouteErrorFallback({
  reset,
  title = "Something went wrong",
  description = "An unexpected error occurred.",
  homeHref,
  homeLabel,
  fill,
}: RouteErrorFallbackProps) {
  return (
    <div
      className={`flex ${fill === "screen" ? "h-screen" : "h-full"} flex-col items-center justify-center gap-4`}
    >
      <EmptyState icon={AlertTriangle} animation="wiggle" title={title} description={description} />
      <div className="flex gap-2">
        <Button variant="secondary" onClick={reset}>
          Try again
        </Button>
        {homeHref && homeLabel && (
          <Button variant="ghost" href={homeHref}>
            {homeLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
