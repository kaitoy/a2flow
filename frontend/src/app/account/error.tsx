"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import logger from "@/lib/logger";

/**
 * Error boundary for `/account`. Renders inside `AccountLayout` (not the
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
  useEffect(() => {
    logger.error(error, "uncaught render error");
  }, [error]);

  return (
    <RouteErrorFallback reset={reset} fill="full" homeHref="/admin" homeLabel="Back to dashboard" />
  );
}
