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
}

/**
 * Breadcrumb trail for admin pages, showing the path back to parent list
 * screens. The last item always renders as plain text (the current page),
 * regardless of whether it has an `href`.
 */
export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1.5 text-xs">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <li key={`${item.href ?? ""}-${item.label}`} className="flex items-center gap-1.5">
              {item.href && !isLast ? (
                <Link
                  href={item.href}
                  className="text-on-surface-variant transition-colors hover:text-accent"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  aria-current={isLast ? "page" : undefined}
                  className="text-on-surface-variant"
                >
                  {item.label}
                </span>
              )}
              {!isLast && (
                <ChevronRight
                  size={14}
                  strokeWidth={1.8}
                  aria-hidden="true"
                  className="text-on-surface-variant/70"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
