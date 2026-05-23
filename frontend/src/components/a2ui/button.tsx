import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { Button } from "../ui/button";

/** A2UI Button implementation that maps the A2UI variant to the design-system Button. */
export const customButton = createComponentImplementation(ButtonApi, ({ props, buildChild }) => {
  const variant =
    props.variant === "primary"
      ? "primary"
      : props.variant === "borderless"
        ? "secondary"
        : "ghost";

  return (
    <Button
      variant={variant}
      onClick={props.action as React.MouseEventHandler<HTMLButtonElement>}
      disabled={props.isValid === false}
    >
      {props.child ? buildChild(props.child) : null}
    </Button>
  );
});
