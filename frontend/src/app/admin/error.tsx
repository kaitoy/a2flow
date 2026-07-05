"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import logger from "@/lib/logger";

/**
 * Error boundary for `/admin/*` routes. Renders inside `AdminLayout` (not the
 * layout itself), so the sidebar and header stay mounted — only the content
 * area swaps to this fallback.
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
