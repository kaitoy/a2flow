import { useState } from 'react';
import { createComponentImplementation } from '@a2ui/react/v0_9';
import { ChoicePickerApi } from '@a2ui/web_core/v0_9/basic_catalog';

export const customChoicePicker = createComponentImplementation(ChoicePickerApi, ({ props, context }) => {
  const [filter, setFilter] = useState('');
  const values = Array.isArray(props.value) ? props.value : [];
  const isMutuallyExclusive = props.variant === 'mutuallyExclusive';
  const isChips = props.displayStyle === 'chips';
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
      filter === '' ||
      String(opt.label).toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-2 w-full">
      {props.label && (
        <strong className="text-sm font-semibold text-gray-700">{String(props.label)}</strong>
      )}
      {props.filterable && (
        <input
          type="text"
          placeholder="Filter options..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      )}
      <div className={isChips ? 'flex flex-row flex-wrap gap-2' : 'flex flex-col gap-2'}>
        {options.map((opt, i) => {
          const isSelected = values.includes(opt.value);
          if (isChips) {
            return (
              <button
                key={i}
                onClick={() => onToggle(String(opt.value))}
                className={
                  isSelected
                    ? 'px-3 py-1 rounded-full text-sm bg-blue-600 text-white border border-blue-600 cursor-pointer'
                    : 'px-3 py-1 rounded-full text-sm bg-white text-gray-700 border border-gray-300 hover:border-blue-400 cursor-pointer'
                }
              >
                {String(opt.label)}
              </button>
            );
          }
          return (
            <label key={i} className="flex items-center gap-2 cursor-pointer">
              <input
                type={isMutuallyExclusive ? 'radio' : 'checkbox'}
                checked={isSelected}
                onChange={() => onToggle(String(opt.value))}
                name={isMutuallyExclusive ? name : undefined}
                className="h-4 w-4 accent-blue-600"
              />
              <span className="text-sm text-gray-700">{String(opt.label)}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
});
