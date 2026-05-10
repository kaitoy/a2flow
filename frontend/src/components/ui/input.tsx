import type React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const BASE =
  "block w-full rounded-xl glass-panel px-4 py-2.5 " +
  "text-sm text-on-surface placeholder:text-on-surface-variant/60 " +
  "transition-all duration-150 " +
  "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export function Input({ className, ...rest }: InputProps) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return <input className={cls} {...rest} />;
}
