import { useState, useId, useEffect } from 'react';
import {
  createComponentImplementation,
  basicCatalog,
  useMarkdownRenderer,
} from '@a2ui/react/v0_9';
import { Catalog } from '@a2ui/web_core/v0_9';
import {
  TextApi,
  ButtonApi,
  CardApi,
  RowApi,
  ColumnApi,
  TextFieldApi,
  ChoicePickerApi,
  BASIC_FUNCTIONS,
} from '@a2ui/web_core/v0_9/basic_catalog';
import type { ReactComponentImplementation } from '@a2ui/react/v0_9';

// ---- Text ----------------------------------------------------------------

const VARIANT_CLASS: Record<string, string> = {
  h1: 'text-2xl font-bold text-gray-900 mt-1',
  h2: 'text-xl  font-bold text-gray-900 mt-1',
  h3: 'text-lg  font-semibold text-gray-900 mt-1',
  h4: 'text-base font-semibold text-gray-900',
  h5: 'text-sm  font-semibold text-gray-900',
  body: 'text-sm text-gray-700 leading-relaxed',
  caption: 'text-xs text-gray-500',
};

const customText = createComponentImplementation(TextApi, ({ props }) => {
  const renderer = useMarkdownRenderer();
  const [html, setHtml] = useState<string | null>(null);
  const text = typeof props.text === 'string' ? props.text : '';
  const cls = VARIANT_CLASS[props.variant ?? 'body'] ?? VARIANT_CLASS.body;

  useEffect(() => {
    if (!renderer) { setHtml(null); return; }
    let active = true;
    renderer(text).then((result) => { if (active) setHtml(result); });
    return () => { active = false; };
  }, [renderer, text]);

  if (props.variant === 'caption') {
    return (
      <span
        className={cls}
        {...(html ? { dangerouslySetInnerHTML: { __html: html } } : {})}
      >
        {html ? undefined : text}
      </span>
    );
  }
  return (
    <div
      className={`${cls} prose prose-sm max-w-none`}
      {...(html ? { dangerouslySetInnerHTML: { __html: html } } : {})}
    >
      {html ? undefined : text}
    </div>
  );
});

// ---- Button --------------------------------------------------------------

const customButton = createComponentImplementation(ButtonApi, ({ props, buildChild }) => {
  const base = 'inline-flex items-center cursor-pointer rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const variant =
    props.variant === 'primary'
      ? 'px-4 py-2 bg-blue-600 text-white border-0 hover:bg-blue-700'
      : props.variant === 'borderless'
        ? 'px-2 py-1 text-blue-600 bg-transparent border-0 hover:underline'
        : 'px-4 py-2 bg-white text-gray-700 border border-gray-300 hover:bg-gray-50';

  return (
    <button
      className={`${base} ${variant}`}
      onClick={props.action as React.MouseEventHandler<HTMLButtonElement>}
      disabled={props.isValid === false}
    >
      {props.child ? buildChild(props.child) : null}
    </button>
  );
});

// ---- Card ----------------------------------------------------------------

const customCard = createComponentImplementation(CardApi, ({ props, buildChild }) => (
  <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4 w-full">
    {props.child ? buildChild(props.child) : null}
  </div>
));

// ---- Row / Column --------------------------------------------------------

const JUSTIFY: Record<string, string> = {
  center: 'justify-center',
  end: 'justify-end',
  spaceAround: 'justify-around',
  spaceBetween: 'justify-between',
  spaceEvenly: 'justify-evenly',
  start: 'justify-start',
  stretch: 'justify-stretch',
};
const ALIGN: Record<string, string> = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  stretch: 'items-stretch',
};

const customRow = createComponentImplementation(RowApi, ({ props, buildChild, context }) => {
  const justify = JUSTIFY[props.justify ?? ''] ?? '';
  const align = ALIGN[props.align ?? ''] ?? '';
  return (
    <div className={`flex flex-row w-full gap-2 ${justify} ${align}`}>
      {(Array.isArray(props.children) ? props.children : []).map((child, i) => (
        <div key={i} className="flex-1 min-w-0">
          {typeof child === 'string'
            ? buildChild(child)
            : child && typeof child === 'object' && 'id' in child
              ? buildChild((child as { id: string }).id, (child as { basePath?: string }).basePath)
              : null}
        </div>
      ))}
    </div>
  );
});

const customColumn = createComponentImplementation(ColumnApi, ({ props, buildChild, context }) => {
  const justify = JUSTIFY[props.justify ?? ''] ?? '';
  const align = ALIGN[props.align ?? ''] ?? '';
  return (
    <div className={`flex flex-col w-full gap-2 ${justify} ${align}`}>
      {(Array.isArray(props.children) ? props.children : []).map((child, i) => (
        <div key={i}>
          {typeof child === 'string'
            ? buildChild(child)
            : child && typeof child === 'object' && 'id' in child
              ? buildChild((child as { id: string }).id, (child as { basePath?: string }).basePath)
              : null}
        </div>
      ))}
    </div>
  );
});

// ---- TextField -----------------------------------------------------------

const customTextField = createComponentImplementation(TextFieldApi, ({ props }) => {
  const id = useId();
  const isLong = props.variant === 'longText';
  const type =
    props.variant === 'number' ? 'number' : props.variant === 'obscured' ? 'password' : 'text';
  const inputCls =
    'block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm ' +
    'focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';
  const hasError = props.validationErrors && props.validationErrors.length > 0;

  return (
    <div className="flex flex-col gap-1 w-full">
      {props.label && (
        <label htmlFor={id} className="text-sm font-medium text-gray-700">
          {props.label}
        </label>
      )}
      {isLong ? (
        <textarea
          id={id}
          className={inputCls}
          rows={4}
          value={props.value ?? ''}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      ) : (
        <input
          id={id}
          type={type}
          className={inputCls}
          value={props.value ?? ''}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      )}
      {hasError && (
        <span className="text-xs text-red-600">{props.validationErrors![0]}</span>
      )}
    </div>
  );
});

// ---- ChoicePicker --------------------------------------------------------

const customChoicePicker = createComponentImplementation(ChoicePickerApi, ({ props, context }) => {
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

// ---- Custom catalog -------------------------------------------------------

const OVERRIDDEN = new Set([
  'Text', 'Button', 'Card', 'Row', 'Column', 'TextField', 'ChoicePicker',
]);

const remainingComponents = Array.from(basicCatalog.components.values()).filter(
  (c) => !OVERRIDDEN.has(c.name),
);

export const tailwindCatalog = new Catalog<ReactComponentImplementation>(
  'https://a2ui.org/specification/v0_9/basic_catalog.json',
  [
    customText,
    customButton,
    customCard,
    customRow,
    customColumn,
    customTextField,
    customChoicePicker,
    ...remainingComponents,
  ],
  BASIC_FUNCTIONS,
);
