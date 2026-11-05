"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import { useT } from "@/i18n/provider";

/**
 * Error boundary for `/profile`. Renders inside `ProfileLayout` (not the
 * layout itself), so the shared `AppHeader` stays mounted — only the page
 * content swaps to this fallback.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useT();
  useEffect(() => {
    console.error("uncaught render error", error);
  }, [error]);

  return (
    <RouteErrorFallback
      reset={reset}
      fill="full"
      homeHref="/"
      homeLabel={t("common.backToDashboard")}
    />
  );
}
