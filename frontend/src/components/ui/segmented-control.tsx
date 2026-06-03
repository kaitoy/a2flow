"use client";

/** A single selectable option within a {@link SegmentedControl}. */
export interface SegmentedOption<T extends string> {
  /** Value reported to `onChange` when this option is selected. */
  value: T;
  /** Visible label for the option. */
  label: string;
}

/** Props for {@link SegmentedControl}. */
export interface SegmentedControlProps<T extends string> {
  /** Selectable options, rendered left to right. */
  options: ReadonlyArray<SegmentedOption<T>>;
  /** Currently selected value. */
  value: T;
  /** Called with the new value when the user selects a different option. */
  onChange: (value: T) => void;
  /** Accessible label describing what the control switches between. */
  "aria-label": string;
  /** Optional extra class names for the container. */
  className?: string;
}

/**
 * A compact glass-panel toggle that switches between a small set of mutually
 * exclusive options (e.g. Table vs Graph). Implemented as a `tablist` so it is
 * keyboard and screen-reader friendly.
 *
 * @param props - The options, current value, and change handler.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  "aria-label": ariaLabel,
  className,
}: SegmentedControlProps<T>) {
  const containerClass = ["inline-flex gap-1 rounded-full glass-panel p-1", className]
    .filter(Boolean)
    .join(" ");

  return (
    // biome-ignore lint/a11y/useFocusableInteractive: tablist role is correct for a segmented control
    <div role="tablist" aria-label={ariaLabel} className={containerClass}>
      {options.map((option) => {
        const selected = option.value === value;
        const buttonClass = [
          "cursor-pointer rounded-full px-3 py-1 text-sm transition-colors",
          "duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
          selected
            ? "bg-accent text-white shadow-sm"
            : "text-on-surface-variant hover:text-on-surface",
        ].join(" ");

        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            className={buttonClass}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
