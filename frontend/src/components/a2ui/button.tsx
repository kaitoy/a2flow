import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { Button } from "../ui/button";

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
