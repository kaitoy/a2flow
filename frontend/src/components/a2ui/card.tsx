import { createComponentImplementation } from '@a2ui/react/v0_9';
import { CardApi } from '@a2ui/web_core/v0_9/basic_catalog';

export const customCard = createComponentImplementation(CardApi, ({ props, buildChild }) => (
  <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4 w-full">
    {props.child ? buildChild(props.child) : null}
  </div>
));
