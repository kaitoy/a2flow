import type React from "react";
import type { TagColor } from "@/lib/api";
import { TAG_COLOR_CLASS } from "@/lib/tag-palette";

/** A single selectable option in a {@link CheckboxGroup}. */
export interface CheckboxOption {
  /** Stable value stored in the group's selection array. */
  value: string;
  /** Human-readable label shown next to the checkbox. */
  label: string;
  /**
   * Palette slot drawn as a small dot before the label. Purely decorative — the
   * label stays the option's accessible name — so a group of tags reads as the
   * same colors the chips elsewhere on the page use.
   */
  swatch?: TagColor;
  /**
   * When true the checkbox cannot be toggled; its current checked state is kept
   * (used for selections the viewer may see but not change, e.g. a role only a
   * super admin may grant or revoke).
   */
  disabled?: boolean;
  /**
   * When true, renders a thin divider above this option, visually separating
   * it from the previous one (e.g. splitting a mutually-exclusive option from
   * the rest of the group).
   */
  dividerBefore?: boolean;
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
  /**
   * Drop the surrounding glass panel, leaving a bare list of rows. Set this when
   * the group already sits inside a glass surface of its own (a popover, say),
   * where a second panel would stack two elevation tiers on top of each other.
   */
  flush?: boolean;
}

const ROW =
  "flex items-center gap-2.5 rounded-lg px-3 py-2 cursor-pointer " +
  "text-sm text-on-surface transition-colors duration-150 " +
  "hover:bg-accent-soft/40";

const ROW_DISABLED =
  "flex items-center gap-2.5 rounded-lg px-3 py-2 cursor-not-allowed " +
  "text-sm text-on-surface-variant transition-colors duration-150";

const DIVIDER_BEFORE = "mt-1.5 border-t border-divider/60 pt-2.5";

/**
 * Controlled multi-select rendered as a vertical list of labeled checkboxes.
 *
 * Toggling a checkbox calls {@link CheckboxGroupProps.onChange} with the updated
 * selection array (values are added in option order and removed in place). Each
 * checkbox's accessible name is its option label, so it can be queried by role
 * and name. Options marked `disabled` render as read-only checkboxes that keep
 * their current state. An option marked `dividerBefore` renders a thin divider
 * above it, splitting the list into visually distinct groups. Pass `flush` to
 * drop the glass panel when the group is already inside one.
 */
export function CheckboxGroup({
  options,
  value,
  onChange,
  emptyMessage = "No options available.",
  name,
  flush = false,
}: CheckboxGroupProps) {
  if (options.length === 0) {
    return (
      <p
        className={
          flush
            ? "px-3 py-2 text-sm text-on-surface-variant"
            : "rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant"
        }
      >
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
    <div
      className={
        flush ? "flex flex-col gap-0.5" : "flex flex-col gap-0.5 rounded-xl glass-panel p-1.5"
      }
    >
      {options.map((option) => (
        <label
          key={option.value}
          className={`${option.disabled ? ROW_DISABLED : ROW}${
            option.dividerBefore ? ` ${DIVIDER_BEFORE}` : ""
          }`}
        >
          <input
            type="checkbox"
            name={name}
            disabled={option.disabled}
            className="size-4 shrink-0 accent-accent disabled:cursor-not-allowed disabled:opacity-60"
            checked={value.includes(option.value)}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              toggle(option.value, e.target.checked)
            }
          />
          {option.swatch && (
            <span
              aria-hidden="true"
              className={`size-2.5 shrink-0 rounded-full tag-swatch ${TAG_COLOR_CLASS[option.swatch]}`}
            />
          )}
          <span className="min-w-0 truncate">{option.label}</span>
        </label>
      ))}
    </div>
  );
}
