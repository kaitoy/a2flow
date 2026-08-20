import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ChoicePickerApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useState } from "react";
import { Select } from "../ui/select";
import { useSurfaceResolved } from "./surfaceResolvedContext";

/**
 * Option count at or above which a single-choice picker is collapsed into a
 * dropdown instead of a radio list. A2UI v0.9 has no dropdown component and its
 * `displayStyle` enum is only `checkbox` | `chips`, so the presentation is
 * decided here from the option count rather than declared by the agent.
 */
const DROPDOWN_OPTION_THRESHOLD = 5;

/** Trigger text shown by the dropdown while nothing is selected yet. */
const DROPDOWN_PLACEHOLDER = "Select an option";

/**
 * A2UI ChoicePicker implementation with dropdown, chips and radio/checkbox display styles
 * and optional filtering. A single-choice picker (`mutuallyExclusive`) that is not
 * explicitly styled as chips renders as the design-system {@link Select} dropdown once it
 * offers {@link DROPDOWN_OPTION_THRESHOLD} options or more, so a long list of allowed
 * values (EC2 instance types, regions, …) does not bury the conversation under radio
 * buttons; shorter lists and multi-select stay as radios/checkboxes. Options are inert when
 * the surface is already resolved (see {@link useSurfaceResolved}), so an already-answered
 * surface's selection can never change.
 */
export const customChoicePicker = createComponentImplementation(
  ChoicePickerApi,
  ({ props, context }) => {
    const [filter, setFilter] = useState("");
    const resolved = useSurfaceResolved();
    const values = Array.isArray(props.value) ? props.value : [];
    const isMutuallyExclusive = props.variant === "mutuallyExclusive";
    const isChips = props.displayStyle === "chips";
    const name = `choice-${context.componentModel.id}`;
    const allOptions = props.options ?? [];
    // Decided from the unfiltered count so typing in the filter box cannot flip
    // the control back to radios halfway through choosing.
    const isDropdown =
      isMutuallyExclusive && !isChips && allOptions.length >= DROPDOWN_OPTION_THRESHOLD;

    const onToggle = (val: string) => {
      if (resolved) return;
      if (isMutuallyExclusive) {
        props.setValue([val] as string[]);
      } else {
        const strValues = values as string[];
        const next = strValues.includes(val)
          ? strValues.filter((v) => v !== val)
          : [...strValues, val];
        props.setValue(next);
      }
    };

    const options = allOptions.filter(
      (opt) =>
        !props.filterable ||
        filter === "" ||
        String(opt.label).toLowerCase().includes(filter.toLowerCase())
    );

    const selected = String(values[0] ?? "");
    const selectOptions = options.map((opt) => ({
      value: opt.value,
      label: String(opt.label),
    }));
    // The filter narrows what the dropdown lists, so re-add the selected option
    // when it is filtered out — otherwise the trigger would blank out and read
    // as "nothing selected" while a value is in fact bound.
    if (selected !== "" && !selectOptions.some((opt) => opt.value === selected)) {
      const hidden = allOptions.find((opt) => opt.value === selected);
      if (hidden) {
        selectOptions.unshift({ value: hidden.value, label: String(hidden.label) });
      }
    }

    return (
      <div className="flex flex-col gap-2 w-full">
        {props.label && <strong className="text-label-caps">{String(props.label)}</strong>}
        {props.filterable && (
          <input
            type="text"
            placeholder="Filter options..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded-xl glass-panel px-3 py-2 text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
        )}
        {isDropdown ? (
          <Select
            options={selectOptions}
            value={selected}
            onChange={onToggle}
            disabled={resolved}
            aria-label={props.label ? String(props.label) : undefined}
            placeholder={DROPDOWN_PLACEHOLDER}
          />
        ) : (
          <div className={isChips ? "flex flex-row flex-wrap gap-2" : "flex flex-col gap-2"}>
            {options.map((opt) => {
              const isSelected = values.includes(opt.value);
              if (isChips) {
                return (
                  <button
                    type="button"
                    key={String(opt.value)}
                    disabled={resolved}
                    onClick={() => onToggle(String(opt.value))}
                    className={[
                      "cursor-pointer rounded-full px-3.5 py-1.5 text-sm tracking-tight transition-all duration-150 motion-safe:hover:scale-[1.03]",
                      "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100",
                      isSelected
                        ? "bg-gradient-to-br from-accent to-secondary text-on-primary shadow-[inset_0_1px_0_var(--inner-top-highlight)]"
                        : "glass-panel text-on-surface hover:text-accent",
                    ].join(" ")}
                  >
                    {String(opt.label)}
                  </button>
                );
              }
              return (
                <label
                  key={String(opt.value)}
                  className={[
                    "flex items-center gap-2",
                    resolved ? "cursor-not-allowed opacity-50" : "cursor-pointer",
                  ].join(" ")}
                >
                  <input
                    type={isMutuallyExclusive ? "radio" : "checkbox"}
                    checked={isSelected}
                    disabled={resolved}
                    onChange={() => onToggle(String(opt.value))}
                    name={isMutuallyExclusive ? name : undefined}
                    className="h-4 w-4 accent-accent"
                  />
                  <span className="text-sm text-on-surface">{String(opt.label)}</span>
                </label>
              );
            })}
          </div>
        )}
      </div>
    );
  }
);
