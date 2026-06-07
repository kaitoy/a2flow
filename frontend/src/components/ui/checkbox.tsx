import React from "react";

/** Props for {@link Checkbox}. */
interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Human-readable label shown next to the checkbox. */
  label: string;
}

const ROW =
  "flex w-fit items-center gap-2.5 rounded-lg px-3 py-2 cursor-pointer " +
  "text-sm text-on-surface transition-colors duration-150 " +
  "hover:bg-accent-soft/40";

/**
 * A single controlled, labeled checkbox primitive.
 *
 * Wraps a native checkbox in a clickable label using the same row styling as
 * {@link CheckboxGroup}, so independent boolean toggles stay visually consistent
 * with multi-select groups. Forwards its ref to the underlying input for
 * `react-hook-form` registration. The accessible name is the {@link label}.
 */
export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className, ...rest },
  ref
) {
  const cls = className ? `${ROW} ${className}` : ROW;
  return (
    <label className={cls}>
      <input ref={ref} type="checkbox" className="size-4 shrink-0 accent-accent" {...rest} />
      <span>{label}</span>
    </label>
  );
});
