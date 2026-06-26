/** @module DeleteIconButton — Icon-only delete action for admin list tables. */
"use client";

import { Tooltip } from "@/components/ui/tooltip";

/** Props for {@link DeleteIconButton}. */
interface DeleteIconButtonProps {
  /** Invoked when the button is clicked (typically opens a confirm dialog). */
  onClick: () => void;
  /** Accessible name and tooltip text. Defaults to `"Delete"`. */
  label?: string;
  /** When true, the button is disabled and does not respond to clicks. */
  disabled?: boolean;
}

/**
 * Compact, label-less delete button for the Actions column of admin list tables.
 *
 * Renders a ✕ glyph styled in the error color, wrapped in a {@link Tooltip} that
 * reveals the label on hover/focus. The `aria-label` keeps the button's
 * accessible name intact for assistive tech and tests.
 */
export function DeleteIconButton({ onClick, label = "Delete", disabled }: DeleteIconButtonProps) {
  return (
    <Tooltip label={label}>
      <button
        type="button"
        aria-label={label}
        onClick={onClick}
        disabled={disabled}
        className={[
          "glass-panel flex size-8 shrink-0 items-center justify-center rounded-lg",
          "cursor-pointer text-on-surface-variant",
          "transition-[background-color,border-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
          "hover:border-error/40 hover:bg-error/10 hover:text-error motion-safe:hover:-translate-y-0.5",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error/50",
          "disabled:cursor-default disabled:opacity-50",
          "disabled:hover:translate-y-0 disabled:hover:border-[var(--color-glass-border)] disabled:hover:bg-transparent disabled:hover:text-on-surface-variant",
        ].join(" ")}
      >
        <span aria-hidden="true" className="text-[14px] leading-none">
          ✕
        </span>
      </button>
    </Tooltip>
  );
}
