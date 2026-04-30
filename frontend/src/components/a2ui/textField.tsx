import { useId } from 'react';
import { createComponentImplementation } from '@a2ui/react/v0_9';
import { TextFieldApi } from '@a2ui/web_core/v0_9/basic_catalog';

export const customTextField = createComponentImplementation(TextFieldApi, ({ props }) => {
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
