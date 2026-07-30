/** @module HeaderIconButton — Icon-only control for an admin page header's action cluster. */
"use client";

import type { ButtonHTMLAttributes, Ref } from "react";
import { Tooltip } from "@/components/ui/tooltip";

/** Props for {@link HeaderIconButton}. */
export interface HeaderIconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible name and tooltip text. */
  label: string;
  /** Forwarded to the underlying `<button>`, e.g. to anchor a popover to it. */
  ref?: Ref<HTMLButtonElement>;
}

/**
 * Round glass icon button sitting in an `AdminPageHeader`'s right-hand action
 * cluster, next to the "Add" button — the refresh control and the column
 * picker's trigger.
 *
 * Distinct from `ActionIconButton`, which is the smaller squared-off variant
 * used inside a table row's Actions column. The label is both the tooltip text
 * and the accessible name, since the button carries no visible text. Any other
 * button attribute (`onClick`, `disabled`, `aria-expanded`, …) passes straight
 * through, and `ref` reaches the `<button>` itself so a caller can anchor a
 * floating panel to it.
 */
export function HeaderIconButton({ label, ref, className, ...rest }: HeaderIconButtonProps) {
  const classes = [
    "inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-full",
    "glass-panel text-on-surface",
    "transition-[transform,translate,scale,box-shadow,color,background-color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
    "hover:shadow-glow hover:text-accent motion-safe:hover:scale-105 motion-safe:active:scale-95",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
    "disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Tooltip label={label} placement="bottom">
      <button ref={ref} type="button" aria-label={label} className={classes} {...rest} />
    </Tooltip>
  );
}
