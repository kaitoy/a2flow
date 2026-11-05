"use client";

import { SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useT } from "@/i18n/provider";

/**
 * Branded 404 for any URL that matches no route in the app. Next.js only
 * ever renders the root `not-found.tsx` for an unmatched URL (nested
 * `not-found.tsx` files only activate on an explicit `notFound()` call within
 * their own subtree), so this single file covers the whole app.
 */
export default function NotFound() {
  const t = useT();
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={SearchX}
        title={t("app.pageNotFound")}
        description={t("app.thePageYoureLookingForDoesntExist")}
      />
      <Button variant="secondary" href="/">
        {t("app.goToHome")}
      </Button>
    </div>
  );
}
