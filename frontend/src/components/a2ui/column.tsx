import { createComponentImplementation } from '@a2ui/react/v0_9';
import { ColumnApi } from '@a2ui/web_core/v0_9/basic_catalog';

const JUSTIFY: Record<string, string> = {
  center: 'justify-center',
  end: 'justify-end',
  spaceAround: 'justify-around',
  spaceBetween: 'justify-between',
  spaceEvenly: 'justify-evenly',
  start: 'justify-start',
  stretch: 'justify-stretch',
};
const ALIGN: Record<string, string> = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  stretch: 'items-stretch',
};

export const customColumn = createComponentImplementation(ColumnApi, ({ props, buildChild }) => {
  const justify = JUSTIFY[props.justify ?? ''] ?? '';
  const align = ALIGN[props.align ?? ''] ?? '';
  return (
    <div className={`flex flex-col w-full gap-2 ${justify} ${align}`}>
      {(Array.isArray(props.children) ? props.children : []).map((child, i) => (
        <div key={i}>
          {typeof child === 'string'
            ? buildChild(child)
            : child && typeof child === 'object' && 'id' in child
              ? buildChild((child as { id: string }).id, (child as { basePath?: string }).basePath)
              : null}
        </div>
      ))}
    </div>
  );
});
