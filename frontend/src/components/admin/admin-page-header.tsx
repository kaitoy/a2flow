import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { AnimatedIcon } from "@/components/ui/animated-icon";
import { Tooltip } from "@/components/ui/tooltip";

interface AdminPageHeaderProps {
  title: string;
  /** Optional accent icon shown to the left of the title; twirls occasionally. */
  icon?: LucideIcon;
  addHref?: string;
  addLabel?: string;
  /** When provided, render a refresh button that re-runs the table fetch on click. */
  onRefresh?: () => void;
  /** True while a refresh is in flight; disables the button and spins the icon. */
  refreshing?: boolean;
}

/**
 * Admin list-page header with a title, an optional refresh button, and an
 * optional "Add" link button.
 *
 * Pass `onRefresh` (typically the `reload` returned by `useTableQuery`) to show
 * a refresh control; pass `refreshing` (typically the hook's `loading` flag) so
 * the button disables and its icon spins while a fetch is in flight.
 */
export function AdminPageHeader({
  title,
  icon,
  addHref,
  addLabel,
  onRefresh,
  refreshing = false,
}: AdminPageHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        {icon && (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl glass-panel-strong text-accent shadow-glow">
            <AnimatedIcon icon={icon} animation="spin-occasional" size={22} />
          </span>
        )}
        <h1 className="text-3xl font-semibold tracking-tight text-gradient-accent">{title}</h1>
      </div>
      <div className="flex items-center gap-2">
        {onRefresh && (
          <Tooltip label="Refresh" placement="bottom">
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              aria-label="Refresh"
              className={[
                "inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-full",
                "glass-panel text-on-surface",
                "transition-[transform,translate,scale,box-shadow,color,background-color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
                "hover:shadow-glow hover:text-accent motion-safe:hover:scale-105 motion-safe:active:scale-95",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                "disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100",
              ].join(" ")}
            >
              <RefreshIcon spinning={refreshing} />
            </button>
          </Tooltip>
        )}
        {addHref && addLabel && (
          <Link
            href={addHref}
            className={[
              "inline-flex cursor-pointer items-center gap-1 rounded-xl px-4 py-2",
              "text-sm font-medium tracking-tight text-on-primary",
              "bg-gradient-to-br from-accent to-secondary",
              "shadow-[0_4px_16px_-4px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.4)]",
              "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-glow",
            ].join(" ")}
          >
            {addLabel}
          </Link>
        )}
      </div>
    </div>
  );
}

/** Outline circular-arrow glyph matching the toolbar's icon style; spins while refreshing. */
function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={spinning ? "motion-safe:animate-spin" : undefined}
    >
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}
