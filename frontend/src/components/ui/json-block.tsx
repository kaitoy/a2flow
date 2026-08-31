/**
 * @module JsonBlock — Pretty-printed JSON on the recessed code surface.
 *
 * The one code-block treatment in the app: a mono `<pre>` on
 * `surface-container-high`, capped in height and scrolling inside itself so a
 * large value never stretches the page. Used for whatever the app shows
 * verbatim rather than as fields — a tool call's arguments and result in the
 * chat transcript, a tool's declared output schema on the tool-mock form.
 */

/**
 * Render a value as pretty-printed JSON text.
 *
 * A value that is already a string is shown as-is rather than re-quoted, so a
 * plain-text tool answer stays readable. A value JSON cannot encode (a cycle,
 * a `BigInt`) falls back to `String(value)` instead of throwing.
 *
 * @param value - The parsed value to display.
 * @returns The text to render inside the block.
 */
export function formatJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Props for {@link JsonBlock}. */
export interface JsonBlockProps {
  /** The value to render. Formatted by {@link formatJson}. */
  value: unknown;
  /** Extra classes, e.g. to raise or drop the height cap. */
  className?: string;
}

/**
 * A scrollable, pretty-printed JSON block.
 *
 * @param props - The value to render and any extra classes.
 * @returns The rendered block.
 */
export function JsonBlock({ value, className }: JsonBlockProps) {
  return (
    <pre
      className={`max-h-64 overflow-auto rounded-lg bg-surface-container-high px-3 py-2 font-mono text-xs leading-relaxed text-on-surface${
        className ? ` ${className}` : ""
      }`}
    >
      {formatJson(value)}
    </pre>
  );
}
