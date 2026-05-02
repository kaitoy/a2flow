import { createComponentImplementation } from "@a2ui/react/v0_9";
import { TextFieldApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useId } from "react";

export const customTextField = createComponentImplementation(TextFieldApi, ({ props }) => {
  const id = useId();
  const isLong = props.variant === "longText";
  const type =
    props.variant === "number" ? "number" : props.variant === "obscured" ? "password" : "text";
  const inputCls =
    "block w-full rounded border border-outline px-3 py-2 text-sm text-on-surface " +
    "focus:border-primary-container focus:outline-none";
  const hasError = props.validationErrors && props.validationErrors.length > 0;

  return (
    <div className="flex flex-col gap-1 w-full">
      {props.label && (
        <label
          htmlFor={id}
          className="text-[12px] leading-[16px] font-bold text-on-surface-variant uppercase tracking-[0.04em]"
        >
          {props.label}
        </label>
      )}
      {isLong ? (
        <textarea
          id={id}
          className={inputCls}
          rows={4}
          value={props.value ?? ""}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      ) : (
        <input
          id={id}
          type={type}
          className={inputCls}
          value={props.value ?? ""}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      )}
      {hasError && <span className="text-xs text-error">{props.validationErrors?.[0]}</span>}
    </div>
  );
});
