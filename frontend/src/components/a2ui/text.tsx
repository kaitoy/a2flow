import { createComponentImplementation, useMarkdownRenderer } from "@a2ui/react/v0_9";
import { TextApi } from "@a2ui/web_core/v0_9/basic_catalog";
import { useEffect, useState } from "react";

const VARIANT_CLASS: Record<string, string> = {
  h1: "text-[24px] leading-[32px] font-semibold text-on-surface tracking-[-0.02em] mt-1",
  h2: "text-[18px] leading-[28px] font-semibold text-on-surface tracking-[-0.01em] mt-1",
  h3: "text-[14px] leading-[20px] font-semibold text-on-surface tracking-[0.05em]",
  h4: "text-[14px] leading-[22px] font-semibold text-on-surface",
  h5: "text-[13px] leading-[20px] font-semibold text-on-surface",
  body: "text-[14px] leading-[22px] font-normal text-on-surface",
  caption:
    "text-[12px] leading-[16px] font-bold text-on-surface-variant uppercase tracking-[0.04em]",
};

export const customText = createComponentImplementation(TextApi, ({ props }) => {
  const renderer = useMarkdownRenderer();
  const [html, setHtml] = useState<string | null>(null);
  const text = typeof props.text === "string" ? props.text : "";
  const cls = VARIANT_CLASS[props.variant ?? "body"] ?? VARIANT_CLASS.body;

  useEffect(() => {
    if (!renderer) {
      setHtml(null);
      return;
    }
    let active = true;
    renderer(text).then((result) => {
      if (active) setHtml(result);
    });
    return () => {
      active = false;
    };
  }, [renderer, text]);

  if (props.variant === "caption") {
    return (
      <span className={cls} {...(html ? { dangerouslySetInnerHTML: { __html: html } } : {})}>
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
