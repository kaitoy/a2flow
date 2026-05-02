import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ChoicePickerApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useState } from "react";

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
        {props.label && (
          <strong className="text-[12px] leading-[16px] font-bold text-on-surface-variant uppercase tracking-[0.04em]">
            {String(props.label)}
          </strong>
        )}
        {props.filterable && (
          <input
            type="text"
            placeholder="Filter options..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded border border-outline px-3 py-1.5 text-sm focus:border-primary-container focus:outline-none"
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
                  className={
                    isSelected
                      ? "px-3 py-1 rounded text-sm bg-primary-container text-on-primary-container border border-primary-container cursor-pointer"
                      : "px-3 py-1 rounded text-sm bg-surface-container-high text-on-surface border border-outline-variant hover:bg-surface-container cursor-pointer"
                  }
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
                  className="h-4 w-4 accent-primary-container"
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
