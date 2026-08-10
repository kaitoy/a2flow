/** @module ReadOnlyField — Recessed read-only rendering of a form field's value. */
import type { ReactNode } from "react";

/** Props for {@link ReadOnlyField}. */
export interface ReadOnlyFieldProps {
  /** The value to display in place of the editable control. */
  children: ReactNode;
  /** Extra classes merged onto the `<p>`, e.g. `whitespace-pre-wrap` for multi-line text. */
  className?: string;
}

/**
 * Recessed field surface for a read-only value — the same `outline-variant`
 * border + `surface-dim/40` fill + inset shadow {@link
 * import("../ui/detail-list").DetailItem}'s `<dd>` uses, so a value reads as
 * sunken rather than being mistaken for an editable input and stays visually
 * distinct from its label above it.
 *
 * Drop-in substitute for an `Input`/`Textarea` inside a {@link
 * import("./form-field").FormField} when the viewer's role can see a field
 * but not edit it.
 */
export function ReadOnlyField({ children, className }: ReadOnlyFieldProps) {
  return (
    <p
      className={[
        "min-h-9 break-words rounded-xl border border-outline-variant bg-surface-dim/40 px-3 py-2 text-sm font-medium text-on-surface shadow-[inset_0_1px_2px_var(--inner-track-shadow)]",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </p>
  );
}
