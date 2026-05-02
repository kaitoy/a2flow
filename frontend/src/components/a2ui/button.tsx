import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";

export const customButton = createComponentImplementation(ButtonApi, ({ props, buildChild }) => {
  const base =
    "inline-flex items-center cursor-pointer rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variant =
    props.variant === "primary"
      ? "px-4 py-2 bg-primary-container text-on-primary-container border-0 text-sm font-medium hover:bg-primary"
      : props.variant === "borderless"
        ? "px-4 py-2 bg-white text-primary border border-primary text-xs font-semibold uppercase tracking-[0.04em] hover:bg-surface-container-low"
        : "px-4 py-2 bg-transparent text-primary border-0 text-sm font-medium hover:bg-surface-container-low";

  return (
    <button
      type="button"
      className={`${base} ${variant}`}
      onClick={props.action as React.MouseEventHandler<HTMLButtonElement>}
      disabled={props.isValid === false}
    >
      {props.child ? buildChild(props.child) : null}
    </button>
  );
});
