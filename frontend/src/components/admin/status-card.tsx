/** @module StatusCard — Independent status banner shown above an entity's main detail card. */
"use client";

import type { ReactNode } from "react";

/** Props for {@link StatusCard}. */
interface StatusCardProps {
  /** Accessible name of the card (exposed as its `aria-label`, e.g. "Workflow status"). */
  ariaLabel: string;
  /** The status readout itself — typically a `StatusDot`, or a few placed side by side. */
  children: ReactNode;
  /** Trailing controls (e.g. `ActionIconButton`s), right-aligned. Omitted entirely when not given. */
  actions?: ReactNode;
  /** Error detail shown on its own line below the status row, when present. */
  error?: string | null;
  /** When true, plays the "live-edge" animation — a background operation affecting this status is in flight. */
  live?: boolean;
}

/**
 * Standalone status card rendered above an entity's main form/detail card
 * inside a `FormLayout`: a glass panel with the status readout on the left,
 * optional actions pinned to the right, and an optional error line spanning
 * the full width beneath.
 */
export function StatusCard({ ariaLabel, children, actions, error, live }: StatusCardProps) {
  return (
    <section
      aria-label={ariaLabel}
      className={[
        "mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl glass-panel p-4",
        live ? "live-edge" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      {error && <p className="w-full break-words font-mono text-error text-xs">{error}</p>}
    </section>
  );
}
