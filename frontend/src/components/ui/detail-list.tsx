/** @module DetailList — Shared definition list for displaying read-only entity attributes. */
import type { ReactNode } from "react";

/** Props for {@link DetailList}. */
export interface DetailListProps {
  /** The {@link DetailItem} cells to lay out. */
  children: ReactNode;
  /** Extra classes merged onto the `<dl>`, e.g. the surrounding panel styling. */
  className?: string;
  /**
   * Force a single column even when the container has room for two. Use for
   * pages that must match a sibling single-column admin form, or whose values
   * run long enough (URLs, descriptions) that two columns would look cramped.
   */
  singleColumn?: boolean;
}

/**
 * Definition list for read-only attribute display, one column when cramped
 * and — unless `singleColumn` opts out — two once it has `@xl` (36rem) of
 * room.
 *
 * The breakpoint is a container query against the list's own wrapper, not the
 * viewport, because the same list is used both full-width under a form and
 * inside the 16rem aside of `FormLayout` — on a wide screen a viewport
 * breakpoint would squeeze that aside into two unreadable columns. The wrapper
 * is rendered here rather than expected from the call site so callers with no
 * container ancestor still get the right behaviour.
 *
 * Only the grid is owned here — panel styling (`glass-panel`, padding, radius)
 * is left to the call site via `className`, so the same list can sit inside a
 * form card or stand alone as an audit footer.
 */
export function DetailList({ children, className, singleColumn }: DetailListProps) {
  const gridCols = singleColumn ? "grid-cols-1" : "grid-cols-1 @xl:grid-cols-2";
  const cls = ["grid", gridCols, "gap-4", className].filter(Boolean).join(" ");
  return (
    <div className="@container">
      <dl className={cls}>{children}</dl>
    </div>
  );
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
 * The value is `font-medium`, the same weight the rest of the app uses for a
 * row's primary text, so it doesn't read as barely-there next to the caps
 * label above it. Values wrap mid-word so an unbroken fallback value (a raw
 * user UUID, say) cannot overflow a narrow column.
 */
export function DetailItem({ label, value }: DetailItemProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <dt className="text-label-caps">{label}</dt>
      <dd className="break-words text-sm font-medium text-on-surface">{value}</dd>
    </div>
  );
}
