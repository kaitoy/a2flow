/** @module DetailList — Shared definition list for displaying read-only entity attributes. */
import type { ReactNode } from "react";

/** Props for {@link DetailList}. */
export interface DetailListProps {
  /** The {@link DetailItem} cells to lay out. */
  children: ReactNode;
  /** Extra classes merged onto the `<dl>`, e.g. the surrounding panel styling. */
  className?: string;
}

/**
 * Responsive definition list for read-only attribute display: one column on
 * narrow viewports, two from `sm` up.
 *
 * Only the grid is owned here — panel styling (`glass-panel`, padding, radius)
 * is left to the call site via `className`, so the same list can sit inside a
 * form card or stand alone as an audit footer.
 */
export function DetailList({ children, className }: DetailListProps) {
  const cls = ["grid grid-cols-1 sm:grid-cols-2 gap-4", className].filter(Boolean).join(" ");
  return <dl className={cls}>{children}</dl>;
}

/** Props for {@link DetailItem}. */
export interface DetailItemProps {
  /** The attribute name, rendered as the `<dt>`. */
  label: string;
  /** The attribute value. May be text or a node (e.g. a `DateTime` or badges). */
  value: ReactNode;
}

/**
 * A single labelled cell of a {@link DetailList}. Labels use the shared
 * `text-label-caps` treatment so they read identically to form field labels.
 */
export function DetailItem({ label, value }: DetailItemProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-label-caps">{label}</dt>
      <dd className="text-sm text-on-surface">{value}</dd>
    </div>
  );
}
