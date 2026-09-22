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
 * The label takes the design-system Button's per-variant text color (`on-primary` on
 * `primary`, `on-surface(-variant)` on `secondary`/`ghost`, `accent` on hover). The visible
 * label comes from `buildChild(props.child)`, typically a nested `customText`, which sets
 * its own explicit `color` class — a descendant's own specified color always wins over an
 * ancestor's inherited one regardless of `!important` on the ancestor, so the `Button`'s
 * own `text-*` class wouldn't reach it. `[&_*]:!text-inherit` targets every descendant
 * directly (the rendered `Text`, an `Icon`, etc.) and makes it inherit the Button's color
 * instead. Forcing a fixed color here (e.g. white) would break on the light theme, where
 * `ghost` is transparent and `secondary` is a near-white glass panel.
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
      className="[&_*]:!text-inherit"
    >
      {props.child ? buildChild(props.child) : null}
    </Button>
  );
});
