import { Check } from "lucide-react";
import type React from "react";
import type { AsyncStatus } from "@/hooks/useAsyncAction";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /**
   * Lifecycle stage for a server-submitting button. When set, the label swaps
   * between `children` (idle), {@link pendingLabel}, and {@link doneLabel} without
   * changing the button width. Omit for a plain static button.
   */
  status?: AsyncStatus;
  /** Label shown while `status` is `pending` (e.g. "Saving…"). */
  pendingLabel?: React.ReactNode;
  /** Label shown while `status` is `done` (e.g. "Saved!"). */
  doneLabel?: React.ReactNode;
}

const BASE =
  "inline-flex items-center justify-center cursor-pointer rounded-xl " +
  "text-sm font-medium tracking-tight " +
  "transition-[transform,translate,scale,box-shadow,background-color,color,opacity] " +
  "duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)] " +
  "motion-safe:active:scale-[0.97] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 " +
  "disabled:cursor-not-allowed disabled:active:scale-100";

/**
 * Vivid success treatment for the `done` stage. Overrides the active variant's
 * fill with a solid success-green (clearing any gradient via `bg-none`), adds a
 * matching glow, and plays a one-shot celebratory wiggle. `disabled:!opacity-100`
 * keeps the button bright even though it is held non-interactive while "Saved!"
 * is shown. Motion is gated by `motion-safe`, so reduced-motion users still get
 * the color/checkmark without the shake.
 */
const DONE =
  "!bg-success !bg-none !text-on-primary !border-transparent " +
  "shadow-[0_4px_20px_-2px_var(--color-success)] " +
  "disabled:!opacity-100 disabled:cursor-default " +
  "motion-safe:animate-wiggle";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "px-4 py-2 text-on-primary bg-gradient-to-br from-accent to-secondary " +
    "shadow-[0_4px_16px_-4px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.4)] " +
    "hover:shadow-glow motion-safe:hover:-translate-y-0.5 motion-safe:active:translate-y-0",
  secondary:
    "px-4 py-2 glass-panel text-on-surface hover:text-accent hover:shadow-glow " +
    "motion-safe:hover:-translate-y-0.5",
  ghost:
    "px-3 py-2 text-on-surface-variant bg-transparent hover:bg-glass hover:text-accent " +
    "motion-safe:hover:-translate-y-0.5",
};

/**
 * Done-stage label: a check icon followed by {@link doneLabel}. Kept as a helper
 * so the visible label and its hidden width-reservation copy stay identical.
 */
function doneContent(doneLabel: React.ReactNode): React.ReactNode {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Check className="size-4" aria-hidden />
      {doneLabel}
    </span>
  );
}

/**
 * Base button with ``primary``, ``secondary``, and ``ghost`` style variants.
 *
 * When {@link ButtonProps.status} is provided, the label cycles through the idle
 * (`children`), `pending`, and `done` text. All candidates are stacked in a
 * single grid cell so the button reserves the widest label's width and never
 * reflows (no flicker) as the status changes.
 *
 * The `done` stage is emphasized: the button turns solid success-green with a
 * leading checkmark and a one-shot celebratory wiggle (see {@link DONE}), and is
 * held non-interactive (rendered `disabled`) for as long as "Saved!" is shown so
 * it cannot be re-triggered. The `pending` stage is likewise non-interactive but
 * keeps the standard dimmed `disabled` look.
 */
export function Button({
  variant = "ghost",
  className,
  status,
  pendingLabel,
  doneLabel,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  if (status === undefined) {
    const cls = [BASE, VARIANT[variant], "disabled:opacity-50", className]
      .filter(Boolean)
      .join(" ");
    return (
      <button type="button" disabled={disabled} {...rest} className={cls}>
        {children}
      </button>
    );
  }

  const isDone = status === "done";
  // Both transient stages lock out interaction; `done` additionally stays vivid.
  const nativeDisabled = disabled || status === "pending" || isDone;
  const cls = [BASE, VARIANT[variant], isDone ? DONE : "disabled:opacity-50", className]
    .filter(Boolean)
    .join(" ");

  const current = status === "pending" ? pendingLabel : isDone ? doneContent(doneLabel) : children;
  // Hidden width-reservation copies of every candidate label. `aria-hidden` keeps
  // them out of the accessible name so the button is still found by its visible
  // label (e.g. "Save"); `invisible` hides them visually while claiming width.
  const reserve = "invisible col-start-1 row-start-1";

  return (
    <button type="button" disabled={nativeDisabled} {...rest} className={cls}>
      <span className="grid justify-items-center">
        <span className={reserve} aria-hidden>
          {children}
        </span>
        {pendingLabel != null && (
          <span className={reserve} aria-hidden>
            {pendingLabel}
          </span>
        )}
        {doneLabel != null && (
          <span className={reserve} aria-hidden>
            {doneContent(doneLabel)}
          </span>
        )}
        <span className="col-start-1 row-start-1">{current}</span>
      </span>
    </button>
  );
}
