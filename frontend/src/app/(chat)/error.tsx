"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import logger from "@/lib/logger";

/**
 * Error boundary for `/sessions/new` and `/sessions/[sessionId]`. Renders
 * inside `ChatLayout` (not the layout itself), so `ChatShell`'s sidebar and
 * header stay mounted — only the conversation panel swaps to this fallback.
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
    <RouteErrorFallback
      reset={reset}
      fill="full"
      homeHref="/sessions/new"
      homeLabel="Start a new chat"
    />
  );
}
