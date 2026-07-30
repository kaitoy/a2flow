import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedIcon } from "@/components/ui/animated-icon";
import { Button } from "@/components/ui/button";
import { HeaderIconButton } from "./header-icon-button";

interface AdminPageHeaderProps {
  title: string;
  /** Optional accent icon shown to the left of the title; twirls occasionally. */
  icon?: LucideIcon;
  addHref?: string;
  addLabel?: string;
  /** Optional extra action rendered before the "Add" button (e.g. a dialog trigger). */
  secondaryAction?: ReactNode;
  /**
   * Optional column-visibility control (a `ColumnPicker`) for the page's table,
   * rendered immediately after the refresh button. It has its own slot rather
   * than sharing `secondaryAction` so the action cluster reads the same way on
   * every list page, including the ones already using that slot.
   */
  columnPicker?: ReactNode;
  /** When provided, render a refresh button that re-runs the table fetch on click. */
  onRefresh?: () => void;
  /** True while a refresh is in flight; disables the button and spins the icon. */
  refreshing?: boolean;
}

/**
 * Admin list-page header with a title, an optional refresh button, an optional
 * column picker, and an optional "Add" link button.
 *
 * Pass `onRefresh` (typically the `reload` returned by `useTableQuery`) to show
 * a refresh control; pass `refreshing` (typically the hook's `loading ||
 * refreshing`) so the button disables and its icon spins while a fetch is in
 * flight. Silent background refreshes deliberately leave the button at rest.
 *
 * The right-hand cluster always reads refresh → column picker → secondary
 * action → "Add", whichever of them a page supplies.
 */
export function AdminPageHeader({
  title,
  icon,
  addHref,
  addLabel,
  secondaryAction,
  columnPicker,
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
        <h1 className="font-display text-3xl font-semibold tracking-tight text-gradient-accent">
          {title}
        </h1>
      </div>
      <div className="flex items-center gap-2">
        {onRefresh && (
          <HeaderIconButton
            label="Refresh"
            // Called with no argument on purpose: `reload` takes options, and
            // the click event must not land in them.
            onClick={() => onRefresh()}
            disabled={refreshing}
          >
            <RefreshIcon spinning={refreshing} />
          </HeaderIconButton>
        )}
        {columnPicker}
        {secondaryAction}
        {addHref && addLabel && (
          <Button variant="primary" href={addHref}>
            {addLabel}
          </Button>
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
