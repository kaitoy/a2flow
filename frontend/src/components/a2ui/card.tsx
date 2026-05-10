import { createComponentImplementation } from "@a2ui/react/v0_9";
import { CardApi } from "@a2ui/web_core/v0_9/basic_catalog";

export const customCard = createComponentImplementation(CardApi, ({ props, buildChild }) => (
  <div className="w-full rounded-2xl glass-panel-strong p-5">
    {props.child ? buildChild(props.child) : null}
  </div>
));
