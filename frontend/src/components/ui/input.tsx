import type React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const BASE =
  "block w-full rounded border border-outline px-3 py-2 " +
  "text-sm text-on-surface focus:border-primary-container focus:outline-none " +
  "disabled:opacity-50";

export function Input({ className, ...rest }: InputProps) {
  const cls = className ? `${BASE} ${className}` : BASE;
  return <input className={cls} {...rest} />;
}
