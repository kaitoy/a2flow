/** @module ActionIconButton — Icon-only action for admin list tables (link or button). */
"use client";

import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { Tooltip } from "@/components/ui/tooltip";

/** Props for {@link ActionIconButton}. */
interface ActionIconButtonProps {
  /** Lucide icon component rendered inside the button. */
  icon: LucideIcon;
  /** Accessible name and tooltip text. */
  label: string;
  /** When set, the control renders as a {@link Link} navigating to this href. */
  href?: string;
  /** Click handler used when `href` is not provided (renders a `<button>`). */
  onClick?: () => void;
  /** When true, the button is disabled and does not respond to clicks. */
  disabled?: boolean;
  /** When true, the icon spins (e.g. while an action is in flight). */
  spinning?: boolean;
}

/**
 * Compact, label-less action button for the Actions column of admin list tables.
 *
 * Renders a lucide icon inside a glass panel, wrapped in a {@link Tooltip} that
 * reveals the label on hover/focus. Renders a {@link Link} when `href` is given,
 * otherwise a `<button>` wired to `onClick`. The `aria-label` keeps the control's
 * accessible name intact for assistive tech and tests.
 */
export function ActionIconButton({
  icon: Icon,
  label,
  href,
  onClick,
  disabled,
  spinning,
}: ActionIconButtonProps) {
  const className = [
    "glass-panel flex size-8 shrink-0 items-center justify-center rounded-lg",
    "cursor-pointer text-on-surface-variant",
    "transition-[background-color,border-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
    "hover:border-accent/40 hover:bg-accent/10 hover:text-accent motion-safe:hover:-translate-y-0.5",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
    "disabled:cursor-default disabled:opacity-50",
    "disabled:hover:translate-y-0 disabled:hover:border-[var(--color-glass-border)] disabled:hover:bg-transparent disabled:hover:text-on-surface-variant",
  ].join(" ");

  const iconEl = (
    <Icon aria-hidden="true" className={spinning ? "size-4 motion-safe:animate-spin" : "size-4"} />
  );

  return (
    <Tooltip label={label}>
      {href ? (
        <Link href={href} aria-label={label} className={className}>
          {iconEl}
        </Link>
      ) : (
        <button
          type="button"
          aria-label={label}
          onClick={onClick}
          disabled={disabled}
          className={className}
        >
          {iconEl}
        </button>
      )}
    </Tooltip>
  );
}
