/** @module status-dot — the shared status dot + label used across the admin UI. */

/** Props for {@link StatusDot}. */
export interface StatusDotProps {
  /**
   * Tailwind background-color class for the dot, taken from the owning domain's
   * status map (e.g. `bg-success/80` from `STATUS_DOT_CLASS`). The palette lives
   * with each domain rather than here, so a status keeps one source of truth.
   */
  dotClass: string;
  /** Display-formatted status name rendered next to the dot. */
  label: string;
  /** Extra classes for the label span. Defaults to `capitalize`. */
  labelClassName?: string;
  /** Extra classes for the wrapping row, for spacing at a given call site. */
  className?: string;
}

/**
 * A small colour-coded dot followed by an achromatic status name.
 *
 * Every status readout in the admin UI uses this shape — the colour carries the
 * state so it can be scanned at a glance, while the name stays in the ambient
 * text colour and remains legible. Previously each page hand-wrote the same
 * markup, so the dot's size and gap drifted between them.
 */
export function StatusDot({
  dotClass,
  label,
  labelClassName = "capitalize",
  className,
}: StatusDotProps) {
  return (
    <span className={`flex items-center gap-2${className ? ` ${className}` : ""}`}>
      <span className={`inline-block size-2 shrink-0 rounded-full ${dotClass}`} aria-hidden />
      <span className={labelClassName}>{label}</span>
    </span>
  );
}
