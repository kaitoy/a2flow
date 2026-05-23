import type React from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const BASE =
  "inline-flex items-center justify-center cursor-pointer rounded-xl " +
  "text-sm font-medium tracking-tight transition-all duration-200 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "px-4 py-2 text-on-primary bg-gradient-to-br from-accent to-secondary " +
    "shadow-[0_4px_16px_-4px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.4)] " +
    "hover:shadow-glow hover:-translate-y-0.5 active:translate-y-0",
  secondary: "px-4 py-2 glass-panel text-on-surface hover:text-accent hover:shadow-glow",
  ghost: "px-3 py-2 text-on-surface-variant bg-transparent hover:bg-glass hover:text-accent",
};

/** Base button with ``primary``, ``secondary``, and ``ghost`` style variants. */
export function Button({ variant = "ghost", className, ...rest }: ButtonProps) {
  const cls = [BASE, VARIANT[variant], className].filter(Boolean).join(" ");
  return <button type="button" {...rest} className={cls} />;
}
