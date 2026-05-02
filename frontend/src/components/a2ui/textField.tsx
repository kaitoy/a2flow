import { createComponentImplementation } from "@a2ui/react/v0_9";
import { TextFieldApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useId } from "react";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

export const customTextField = createComponentImplementation(TextFieldApi, ({ props }) => {
  const id = useId();
  const isLong = props.variant === "longText";
  const type =
    props.variant === "number" ? "number" : props.variant === "obscured" ? "password" : "text";
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
        <Textarea
          id={id}
          rows={4}
          value={props.value ?? ""}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      ) : (
        <Input
          id={id}
          type={type}
          value={props.value ?? ""}
          onChange={(e) => props.setValue?.(e.target.value)}
        />
      )}
      {hasError && <span className="text-xs text-error">{props.validationErrors?.[0]}</span>}
    </div>
  );
});
