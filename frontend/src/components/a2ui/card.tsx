import { createComponentImplementation } from "@a2ui/react/v0_9";
import { CardApi } from "@a2ui/web_core/v0_9/basic_catalog";

export const customCard = createComponentImplementation(CardApi, ({ props, buildChild }) => (
  <div className="rounded border border-outline-variant bg-surface-container-lowest p-5 shadow-card w-full">
    {props.child ? buildChild(props.child) : null}
  </div>
));
