"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import logger from "@/lib/logger";

/**
 * App-wide error boundary for anything not caught by a more specific
 * `error.tsx` (`/`, `/login`, `/workflow-sessions/[id]`, or a crash bubbling
 * past the `admin`/`(chat)`/`account` boundaries). Renders inside the root
 * layout, so theme/store providers stay mounted.
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
    <RouteErrorFallback reset={reset} fill="screen" homeHref="/admin" homeLabel="Go to dashboard" />
  );
}
