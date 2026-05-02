import type React from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const BASE =
  "inline-flex items-center cursor-pointer rounded transition-colors " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "px-4 py-2 bg-primary-container text-on-primary-container border-0 " +
    "text-sm font-medium hover:bg-primary",
  secondary:
    "px-4 py-2 bg-white text-primary border border-primary " +
    "text-xs font-semibold uppercase tracking-[0.04em] hover:bg-surface-container-low",
  ghost:
    "px-4 py-2 bg-transparent text-primary border-0 " +
    "text-sm font-medium hover:bg-surface-container-low",
};

export function Button({ variant = "ghost", className, ...rest }: ButtonProps) {
  const cls = [BASE, VARIANT[variant], className].filter(Boolean).join(" ");
  // biome-ignore lint/a11y/useButtonType: type defaults to "button" via defaultProps pattern below
  return <button type="button" {...rest} className={cls} />;
}
