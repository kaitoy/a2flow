import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { Button } from "../ui/button";
import { useSurfaceResolved } from "./surfaceResolvedContext";

/**
 * A2UI Button implementation that maps the A2UI variant to the design-system Button.
 * Disabled when the surface is already resolved (see {@link useSurfaceResolved}), so an
 * already-answered surface can never be resubmitted, in addition to the schema's own
 * `isValid` validity check.
 */
export const customButton = createComponentImplementation(ButtonApi, ({ props, buildChild }) => {
  const resolved = useSurfaceResolved();
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
      disabled={props.isValid === false || resolved}
    >
      {props.child ? buildChild(props.child) : null}
    </Button>
  );
});
