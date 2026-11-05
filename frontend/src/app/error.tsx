"use client";

import { useEffect } from "react";
import { RouteErrorFallback } from "@/components/ui/route-error-fallback";
import { useT } from "@/i18n/provider";

/**
 * App-wide error boundary for anything not caught by a more specific
 * `error.tsx` (`/`, `/login`, `/workflow-executions/[id]/session`, or a crash bubbling
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
  const t = useT();
  useEffect(() => {
    console.error("uncaught render error", error);
  }, [error]);

  return (
    <RouteErrorFallback reset={reset} fill="screen" homeHref="/" homeLabel={t("app.goToHome")} />
  );
}
