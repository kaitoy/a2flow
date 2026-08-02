/** @module Breadcrumbs — Small breadcrumb trail shown above admin page headers. */
import { ChevronRight } from "lucide-react";
import Link from "next/link";

/** A single crumb in a breadcrumb trail. */
export interface BreadcrumbItem {
  /** Label text shown for this crumb. */
  label: string;
  /** Route to link to. Omit on the last (current-page) entry. */
  href?: string;
}

interface BreadcrumbsProps {
  /** Ordered trail from root ("Admin") to the current page. */
  items: BreadcrumbItem[];
  /**
   * Classes for the outer `<nav>`, replacing the default `mb-4` spacing used
   * above a page header. Pass e.g. `""` when embedding the trail inline
   * (such as in `AppHeader`) instead of stacking it above content.
   */
  className?: string;
}

/**
 * Breadcrumb trail for admin pages, showing the path back to parent list
 * screens. The last item always renders as plain text (the current page)
 * and truncates rather than wrapping, since it is the crumb most likely to
 * hold a long, user-provided name; regardless of whether it has an `href`.
 */
export function Breadcrumbs({ items, className = "mb-4" }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className={`min-w-0 ${className}`}>
      <ol className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <li
              key={`${item.href ?? ""}-${item.label}`}
              className="flex min-w-0 items-center gap-1.5"
            >
              {item.href && !isLast ? (
                <Link
                  href={item.href}
                  className="shrink-0 text-on-surface-variant transition-colors hover:text-accent"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  aria-current={isLast ? "page" : undefined}
                  className={`text-on-surface-variant ${isLast ? "truncate" : "shrink-0"}`}
                >
                  {item.label}
                </span>
              )}
              {!isLast && (
                <ChevronRight
                  size={14}
                  strokeWidth={1.8}
                  aria-hidden="true"
                  className="shrink-0 text-on-surface-variant/70"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
