import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { Button } from "../ui/button";
import { useSurfaceResolved } from "./surfaceResolvedContext";

/**
 * A2UI Button implementation that maps the A2UI variant to the design-system Button.
 * Disabled when the surface is already resolved (see {@link useSurfaceResolved}), so an
 * already-answered surface can never be resubmitted, in addition to the schema's own
 * `isValid` validity check.
 *
 * Text is forced to white regardless of variant, overriding the design-system Button's
 * per-variant text color (`on-primary` on `primary` turns dark in the dark theme, and
 * `secondary`/`ghost` default to darker `on-surface(-variant)` text). The visible label
 * comes from `buildChild(props.child)`, typically a nested `customText`, which sets its
 * own explicit `color` class — a descendant's own specified color always wins over an
 * ancestor's inherited one regardless of `!important` on the ancestor, so a plain
 * `text-white` on the `Button` itself wouldn't reach it. `[&_*]:!text-white` targets every
 * descendant directly (the rendered `Text`, an `Icon`, etc.) to force white there instead.
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
      className="[&_*]:!text-white"
    >
      {props.child ? buildChild(props.child) : null}
    </Button>
  );
});
