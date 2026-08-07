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
 * `text-label-caps` treatment so they read identically to form field labels,
 * and the value sits on a **recessed field surface** below it — the same
 * `outline-variant` border + `surface-dim/40` fill + inset shadow the
 * `SegmentedControl` track uses.
 *
 * Without a surface of its own the value loses to its own label: the caps label
 * is the heavier mark, so a stack of bare label/value pairs reads as an
 * undifferentiated column of text. Giving the value a field of its own restores
 * the label/input rhythm of {@link import("../admin/form-field").FormField}, so
 * a read-only page and an editable one share a skeleton. The surface is
 * deliberately recessed rather than raised glass — per DESIGN.md that inversion
 * is what keeps it from being mistaken for an input.
 *
 * `min-h-9` holds the field's height steady across value types (a mono `text-xs`
 * commit SHA, an em-dash placeholder), and values wrap mid-word so an unbroken
 * fallback value (a raw user UUID, say) cannot overflow a narrow column.
 */
export function DetailItem({ label, value }: DetailItemProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <dt className="text-label-caps">{label}</dt>
      <dd className="min-h-9 break-words rounded-xl border border-outline-variant bg-surface-dim/40 px-3 py-2 text-sm font-medium text-on-surface shadow-[inset_0_1px_2px_var(--inner-track-shadow)]">
        {value}
      </dd>
    </div>
  );
}
