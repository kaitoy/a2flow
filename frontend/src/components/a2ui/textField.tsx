import { createComponentImplementation } from "@a2ui/react/v0_9";
import { TextFieldApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useId } from "react";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

/** A2UI TextField implementation that renders a single-line Input or multi-line Textarea based on variant. */
export const customTextField = createComponentImplementation(TextFieldApi, ({ props }) => {
  const id = useId();
  const isLong = props.variant === "longText";
  const type =
    props.variant === "number" ? "number" : props.variant === "obscured" ? "password" : "text";
  const hasError = props.validationErrors && props.validationErrors.length > 0;

  return (
    <div className="flex w-full flex-col gap-1.5">
      {props.label && (
        <label htmlFor={id} className="text-label-caps">
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
