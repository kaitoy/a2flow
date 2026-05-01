import { createComponentImplementation } from "@a2ui/react/v0_9";
import { ButtonApi } from "@a2ui/web_core/v0_9/basic_catalog";

export const customButton = createComponentImplementation(ButtonApi, ({ props, buildChild }) => {
  const base =
    "inline-flex items-center cursor-pointer rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variant =
    props.variant === "primary"
      ? "px-4 py-2 bg-blue-600 text-white border-0 hover:bg-blue-700"
      : props.variant === "borderless"
        ? "px-2 py-1 text-blue-600 bg-transparent border-0 hover:underline"
        : "px-4 py-2 bg-white text-gray-700 border border-gray-300 hover:bg-gray-50";

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
