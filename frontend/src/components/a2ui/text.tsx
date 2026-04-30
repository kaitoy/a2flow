import { useState, useEffect } from 'react';
import { createComponentImplementation, useMarkdownRenderer } from '@a2ui/react/v0_9';
import { TextApi } from '@a2ui/web_core/v0_9/basic_catalog';

const VARIANT_CLASS: Record<string, string> = {
  h1: 'text-2xl font-bold text-gray-900 mt-1',
  h2: 'text-xl  font-bold text-gray-900 mt-1',
  h3: 'text-lg  font-semibold text-gray-900 mt-1',
  h4: 'text-base font-semibold text-gray-900',
  h5: 'text-sm  font-semibold text-gray-900',
  body: 'text-sm text-gray-700 leading-relaxed',
  caption: 'text-xs text-gray-500',
};

export const customText = createComponentImplementation(TextApi, ({ props }) => {
  const renderer = useMarkdownRenderer();
  const [html, setHtml] = useState<string | null>(null);
  const text = typeof props.text === 'string' ? props.text : '';
  const cls = VARIANT_CLASS[props.variant ?? 'body'] ?? VARIANT_CLASS.body;

  useEffect(() => {
    if (!renderer) { setHtml(null); return; }
    let active = true;
    renderer(text).then((result) => { if (active) setHtml(result); });
    return () => { active = false; };
  }, [renderer, text]);

  if (props.variant === 'caption') {
    return (
      <span
        className={cls}
        {...(html ? { dangerouslySetInnerHTML: { __html: html } } : {})}
      >
        {html ? undefined : text}
      </span>
    );
  }
  return (
    <div
      className={`${cls} prose prose-sm max-w-none`}
      {...(html ? { dangerouslySetInnerHTML: { __html: html } } : {})}
    >
      {html ? undefined : text}
    </div>
  );
});
