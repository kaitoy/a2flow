/** @module AdminPageContainer — Shared outer width/alignment wrapper for admin pages. */
import type { ReactNode } from "react";

interface AdminPageContainerProps {
  children: ReactNode;
}

/**
 * Outer wrapper shared by every admin page — list, detail, and create
 * screens alike. Keeping the same max-width and horizontal centering across
 * all of them means breadcrumbs and page titles sit at the same x-position
 * everywhere, so they don't shift when navigating between a wide list page
 * and a narrower detail form. Detail/create pages that need a narrower,
 * centered form card should nest a `FormColumn` inside this container
 * instead of narrowing the container itself.
 */
export function AdminPageContainer({ children }: AdminPageContainerProps) {
  return <div className="mx-auto max-w-6xl p-8">{children}</div>;
}
