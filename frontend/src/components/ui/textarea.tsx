import React from "react";

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const BASE =
  "block w-full rounded-xl glass-panel px-4 py-2.5 " +
  "text-sm text-on-surface placeholder:text-on-surface-variant/60 " +
  "transition-all duration-150 " +
  "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

/** Styled textarea with glass-panel surface, forwarded ref, and focus ring. */
export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, ...rest },
  ref
) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return <textarea ref={ref} className={cls} {...rest} />;
});
