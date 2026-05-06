import type React from "react";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

const BASE =
  "block w-full rounded border border-outline px-3 py-2 " +
  "text-sm text-on-surface focus:border-primary-container focus:outline-none " +
  "disabled:opacity-50 bg-surface";

export function Select({ className, children, ...rest }: SelectProps) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return (
    <select className={cls} {...rest}>
      {children}
    </select>
  );
}
