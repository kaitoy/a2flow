/**
 * @module read-only-display — Formatters turning form values into the plain text a
 * read-only field shows.
 *
 * A detail page a viewer may see but not edit renders every field through
 * {@link import("@/components/admin/read-only-field").ReadOnlyField}, which takes
 * text rather than a control. These helpers produce that text for the value
 * shapes the admin forms hold — booleans, one-of-N choices, and the list/pair
 * editors — so the same rendering does not get re-derived in each field set.
 *
 * Multi-line results are joined with `\n`; render them inside a
 * `ReadOnlyField` carrying `className="whitespace-pre-wrap"`.
 */

/** Placeholder shown in place of an attribute that has no value. */
export const EMPTY_VALUE = "—";

/**
 * Render a boolean flag (an `enabled` checkbox, say) as a word.
 *
 * @param value - The flag's current state.
 * @returns `"Yes"` or `"No"`.
 */
export function formatFlag(value: boolean): string {
  return value ? "Yes" : "No";
}

/**
 * Resolve the visible label of the selected option of a one-of-N control.
 *
 * Pass the very same option list the editable control renders — a
 * `SegmentedControl`'s, typically — so the read-only and editable renderings
 * cannot drift apart.
 *
 * @param options - The available options, in the control's own order.
 * @param value - The currently selected value.
 * @returns The matching option's label, or the raw value when none matches.
 */
export function formatChoice<T extends string>(
  options: ReadonlyArray<{ value: T; label: string }>,
  value: T
): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

/**
 * Join list entries one per line, falling back to the empty placeholder.
 *
 * @param lines - The entries, in display order.
 * @returns The joined text, or {@link EMPTY_VALUE} when there is nothing to show.
 */
export function formatLines(lines: readonly string[]): string {
  return lines.length === 0 ? EMPTY_VALUE : lines.join("\n");
}

/**
 * Render key/value rows as `key: value` lines, dropping unnamed rows.
 *
 * A row whose value is blank shows its key alone rather than a dangling colon —
 * that is the shape a secret's entries come back in, since the API never
 * returns their values.
 *
 * @param pairs - The rows, in display order.
 * @returns One line per named row, ready for {@link formatLines}.
 */
export function formatPairs(pairs: ReadonlyArray<{ key: string; value: string }>): string[] {
  return pairs
    .filter((pair) => pair.key.trim() !== "")
    .map((pair) => (pair.value === "" ? pair.key : `${pair.key}: ${pair.value}`));
}
