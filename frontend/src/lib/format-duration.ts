/** @module format-duration — Compact, localized rendering of a duration given in seconds. */

const UNITS = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
] as const;

/**
 * Format a duration in its largest fitting unit, e.g. `3d`, `1.5h`, `12m`, `45s`.
 *
 * The backend reports every duration in whole seconds; a dashboard has room
 * for one short figure, so the value is shown in a single unit — with one
 * decimal while it is below ten of that unit, none above. `Intl.NumberFormat`
 * supplies the unit suffix, so no message catalog entry is needed.
 *
 * @param seconds - The duration; negative values are treated as zero.
 * @param locale - BCP 47 locale for the number and the unit suffix (`t.locale`).
 * @returns The formatted duration.
 */
export function formatDuration(seconds: number, locale: string): string {
  const value = Math.max(0, seconds);
  const [unit, size] = UNITS.find(([, s]) => value >= s) ?? UNITS[UNITS.length - 1];
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "narrow",
    maximumFractionDigits: value >= size * 10 || unit === "second" ? 0 : 1,
  }).format(value / size);
}
