"use client";

import { ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useT } from "@/i18n/provider";

/** Props for {@link AccessDeniedState}. */
export interface AccessDeniedStateProps {
  /** Headline shown above the description. Defaults to "Access denied". */
  title?: string;
  /** Supporting line beneath the title. */
  description?: string;
  /** `"screen"` fills the viewport (no persistent chrome above/around it); `"full"` fills its parent (a shell's content area stays mounted around it). */
  fill: "screen" | "full";
}

/**
 * Full-page/full-region state for a FORBIDDEN (403) failure on a page's
 * initial data load -- see `isForbiddenError` in `lib/api.ts`. Distinct from
 * `RouteErrorFallback` (a render-crash boundary offering "Try again") and
 * from a generic retryable load-failure state: retrying can't fix a missing
 * permission, so this offers only a way back, via `router.back()`, since the
 * page it replaces is reachable from more than one place.
 */
export function AccessDeniedState({
  title = "ui.accessDenied",
  description = "ui.noPermissionToViewPage",
  fill,
}: AccessDeniedStateProps) {
  const t = useT();
  const router = useRouter();
  return (
    <div
      className={`flex ${fill === "screen" ? "h-dvh" : "h-full"} flex-col items-center justify-center gap-4`}
    >
      <EmptyState
        icon={ShieldAlert}
        animation="none"
        title={t.maybe(title)}
        description={t.maybe(description)}
      />
      <Button variant="secondary" onClick={() => router.back()}>
        {t("ui.goBack")}
      </Button>
    </div>
  );
}
