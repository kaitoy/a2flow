import React from "react";

/** Props for {@link Checkbox}. */
interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Human-readable label shown next to the checkbox. */
  label: string;
  /**
   * Hide the label text and drop the row padding, leaving a bare checkbox whose
   * accessible name is still {@link label}. For dense contexts such as a table
   * cell, where the row's other columns already say what is being checked.
   */
  labelHidden?: boolean;
}

const ROW =
  "flex w-fit items-center gap-2.5 rounded-lg px-3 py-2 cursor-pointer " +
  "text-sm text-on-surface transition-colors duration-150 " +
  "hover:bg-accent-soft/40";

const BARE = "inline-flex cursor-pointer items-center";

/**
 * A single controlled, labeled checkbox primitive.
 *
 * Wraps a native checkbox in a clickable label using the same row styling as
 * {@link CheckboxGroup}, so independent boolean toggles stay visually consistent
 * with multi-select groups. Forwards its ref to the underlying input for
 * `react-hook-form` registration. The accessible name is the {@link label}.
 */
export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, labelHidden, className, ...rest },
  ref
) {
  const base = labelHidden ? BARE : ROW;
  const cls = className ? `${base} ${className}` : base;
  return (
    <label className={cls}>
      <input ref={ref} type="checkbox" className="size-4 shrink-0 accent-accent" {...rest} />
      <span className={labelHidden ? "sr-only" : undefined}>{label}</span>
    </label>
  );
});
