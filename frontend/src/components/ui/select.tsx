import type React from "react";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

const BASE =
  "block w-full rounded-xl glass-panel px-4 py-2.5 " +
  "text-sm text-on-surface " +
  "transition-all duration-150 " +
  "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export function Select({ className, children, ...rest }: SelectProps) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return (
    <select className={cls} {...rest}>
      {children}
    </select>
  );
}
