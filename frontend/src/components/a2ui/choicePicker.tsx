import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ChoicePickerApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useState } from "react";

/** A2UI ChoicePicker implementation with chips and radio/checkbox display styles and optional filtering. */
export const customChoicePicker = createComponentImplementation(
  ChoicePickerApi,
  ({ props, context }) => {
    const [filter, setFilter] = useState("");
    const values = Array.isArray(props.value) ? props.value : [];
    const isMutuallyExclusive = props.variant === "mutuallyExclusive";
    const isChips = props.displayStyle === "chips";
    const name = `choice-${context.componentModel.id}`;

    const onToggle = (val: string) => {
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

    const options = (props.options ?? []).filter(
      (opt) =>
        !props.filterable ||
        filter === "" ||
        String(opt.label).toLowerCase().includes(filter.toLowerCase())
    );

    return (
      <div className="flex flex-col gap-2 w-full">
        {props.label && <strong className="text-label-caps">{String(props.label)}</strong>}
        {props.filterable && (
          <input
            type="text"
            placeholder="Filter options..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded-xl glass-panel px-3 py-2 text-sm text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
        )}
        <div className={isChips ? "flex flex-row flex-wrap gap-2" : "flex flex-col gap-2"}>
          {options.map((opt) => {
            const isSelected = values.includes(opt.value);
            if (isChips) {
              return (
                <button
                  type="button"
                  key={String(opt.value)}
                  onClick={() => onToggle(String(opt.value))}
                  className={[
                    "cursor-pointer rounded-full px-3.5 py-1.5 text-sm tracking-tight transition-all duration-150 motion-safe:hover:scale-[1.03]",
                    isSelected
                      ? "bg-gradient-to-br from-accent to-secondary text-on-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                      : "glass-panel text-on-surface hover:text-accent",
                  ].join(" ")}
                >
                  {String(opt.label)}
                </button>
              );
            }
            return (
              <label key={String(opt.value)} className="flex items-center gap-2 cursor-pointer">
                <input
                  type={isMutuallyExclusive ? "radio" : "checkbox"}
                  checked={isSelected}
                  onChange={() => onToggle(String(opt.value))}
                  name={isMutuallyExclusive ? name : undefined}
                  className="h-4 w-4 accent-accent"
                />
                <span className="text-sm text-on-surface">{String(opt.label)}</span>
              </label>
            );
          })}
        </div>
      </div>
    );
  }
);
