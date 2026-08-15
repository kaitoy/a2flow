import React from "react";

/** Props for {@link Radio}. */
interface RadioProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Human-readable label shown next to the radio. */
  label: string;
  /**
   * Hide the label text and drop the row padding, leaving a bare radio whose
   * accessible name is still {@link label}. For dense contexts such as a table
   * cell, where the row's other columns already say what is being chosen.
   */
  labelHidden?: boolean;
}

const ROW =
  "flex w-fit items-center gap-2.5 rounded-lg px-3 py-2 cursor-pointer " +
  "text-sm text-on-surface transition-colors duration-150 " +
  "hover:bg-accent-soft/40";

const BARE = "inline-flex cursor-pointer items-center";

/**
 * A single controlled, labeled radio primitive.
 *
 * The one-of-many counterpart of {@link Checkbox}, deliberately mirroring it
 * down to the row styling so a single-select list and a multi-select list are
 * visually indistinguishable apart from the control itself. Radios sharing a
 * `name` form one group, within which the browser enforces that at most one is
 * checked — which is exactly the guarantee a checkbox cannot give, and the
 * reason a single-select list must not be built out of checkboxes.
 *
 * Forwards its ref to the underlying input for `react-hook-form` registration.
 * The accessible name is the {@link label}. Pass
 * {@link RadioProps.labelHidden} to render a bare radio for dense contexts,
 * such as a table cell, that already state what is being chosen.
 */
export const Radio = React.forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { label, labelHidden, className, ...rest },
  ref
) {
  const base = labelHidden ? BARE : ROW;
  const cls = className ? `${base} ${className}` : base;
  return (
    <label className={cls}>
      <input ref={ref} type="radio" className="size-4 shrink-0 accent-accent" {...rest} />
      <span className={labelHidden ? "sr-only" : undefined}>{label}</span>
    </label>
  );
});
