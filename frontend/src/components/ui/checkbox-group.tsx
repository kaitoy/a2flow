import type React from "react";

/** A single selectable option in a {@link CheckboxGroup}. */
export interface CheckboxOption {
  /** Stable value stored in the group's selection array. */
  value: string;
  /** Human-readable label shown next to the checkbox. */
  label: string;
}

/** Props for {@link CheckboxGroup}. */
export interface CheckboxGroupProps {
  /** Options to render, one labeled checkbox per entry. */
  options: CheckboxOption[];
  /** Currently selected option values. */
  value: string[];
  /** Called with the next selection array whenever an option is toggled. */
  onChange: (next: string[]) => void;
  /** Message shown when {@link CheckboxGroupProps.options} is empty. */
  emptyMessage?: string;
  /** Optional name applied to each checkbox input. */
  name?: string;
}

const ROW =
  "flex items-center gap-2.5 rounded-lg px-3 py-2 cursor-pointer " +
  "text-sm text-on-surface transition-colors duration-150 " +
  "hover:bg-accent-soft/40";

/**
 * Controlled multi-select rendered as a vertical list of labeled checkboxes.
 *
 * Toggling a checkbox calls {@link CheckboxGroupProps.onChange} with the updated
 * selection array (values are added in option order and removed in place). Each
 * checkbox's accessible name is its option label, so it can be queried by role
 * and name.
 */
export function CheckboxGroup({
  options,
  value,
  onChange,
  emptyMessage = "No options available.",
  name,
}: CheckboxGroupProps) {
  if (options.length === 0) {
    return (
      <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
        {emptyMessage}
      </p>
    );
  }

  function toggle(optionValue: string, checked: boolean) {
    if (checked) {
      onChange(
        options
          .filter((o) => value.includes(o.value) || o.value === optionValue)
          .map((o) => o.value)
      );
    } else {
      onChange(value.filter((v) => v !== optionValue));
    }
  }

  return (
    <div className="flex flex-col gap-0.5 rounded-xl glass-panel p-1.5">
      {options.map((option) => (
        <label key={option.value} className={ROW}>
          <input
            type="checkbox"
            name={name}
            className="size-4 shrink-0 accent-accent"
            checked={value.includes(option.value)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              toggle(option.value, e.target.checked)
            }
          />
          <span>{option.label}</span>
        </label>
      ))}
    </div>
  );
}
