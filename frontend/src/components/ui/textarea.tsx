import React from "react";

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const BASE =
  "block w-full rounded border border-outline px-3 py-2 " +
  "text-sm text-on-surface focus:border-primary-container focus:outline-none " +
  "disabled:opacity-50";

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, ...rest },
  ref
) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return <textarea ref={ref} className={cls} {...rest} />;
});
