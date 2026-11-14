/** @module EmptyState — centered empty-state placeholder with an accent icon. */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedIcon, type IconAnimation } from "./animated-icon";

/** Props for {@link EmptyState}. */
export interface EmptyStateProps {
  /** Accent icon shown in the tile. */
  icon: LucideIcon;
  /** Animation applied to the icon. Defaults to `"none"`. */
  animation?: IconAnimation;
  /** Optional headline, set in the display face. */
  title?: ReactNode;
  /** Optional supporting line beneath the title. */
  description?: ReactNode;
  /**
   * Compact layout for tight containers (sidebars, table cells): smaller tile,
   * less padding, a plain-weight headline. Defaults to `false`.
   */
  compact?: boolean;
  /** Extra classes merged onto the outer wrapper. */
  className?: string;
}

/**
 * Centered placeholder for empty regions (no messages, no rows, no sessions).
 *
 * Pairs an {@link AnimatedIcon} inside a raised tile with an optional
 * title and description so empty screens feel intentional rather than blank.
 * Use `compact` inside narrow containers like the session sidebar or a table's
 * empty cell.
 */
export function EmptyState({
  icon,
  animation = "none",
  title,
  description,
  compact = false,
  className,
}: EmptyStateProps) {
  const wrapperCls = [
    "flex flex-col items-center justify-center text-center select-none",
    compact ? "gap-2 py-2" : "py-20",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const tileCls = compact
    ? "flex h-9 w-9 items-center justify-center rounded-xl glass-panel-strong"
    : "mb-4 flex h-14 w-14 items-center justify-center rounded-2xl glass-panel-strong";

  return (
    <div className={wrapperCls}>
      <div className={tileCls}>
        <AnimatedIcon
          icon={icon}
          animation={animation}
          size={compact ? 18 : 28}
          className="text-accent"
        />
      </div>
      {title &&
        (compact ? (
          <p className="text-xs font-medium text-on-surface">{title}</p>
        ) : (
          <h2 className="font-display mb-1 text-2xl font-semibold tracking-tight text-on-surface">
            {title}
          </h2>
        ))}
      {description && (
        <p
          className={
            compact ? "text-xs text-on-surface-variant" : "text-sm text-on-surface-variant"
          }
        >
          {description}
        </p>
      )}
    </div>
  );
}
