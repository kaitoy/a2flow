/** @module FormColumn — Narrow centered column for a single-record admin form. */
import type { ReactNode } from "react";

interface FormColumnProps {
  children: ReactNode;
}

/**
 * Narrows and centers its content to `max-w-2xl` so a detail/create form
 * (or its loading skeleton, plus trailing audit metadata) reads as a
 * floating card, independent of the wider `AdminPageContainer` it sits
 * inside. This keeps the form visually narrow per DESIGN.md while letting
 * the breadcrumb and title above it stay flush left at the page's full
 * width.
 */
export function FormColumn({ children }: FormColumnProps) {
  return <div className="mx-auto max-w-2xl">{children}</div>;
}
