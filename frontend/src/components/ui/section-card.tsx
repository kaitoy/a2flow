/** @module SectionCard — titled glass card grouping a page section's content under an accent icon. */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedIcon } from "@/components/ui/animated-icon";

/** Props for {@link SectionCard}. */
export interface SectionCardProps {
  /** Accent icon shown in the tile beside the title; twirls occasionally. */
  icon: LucideIcon;
  /** Section heading, rendered as the card's `h2`. */
  title: string;
  /** The section's content, laid out in a column below the heading. */
  children: ReactNode;
  /** Extra classes merged onto the card. */
  className?: string;
}

/**
 * A `glass-panel-strong` card that names the section it holds: an accent icon
 * tile plus an `h2`, then the caller's content.
 *
 * The icon tile reuses the vocabulary of
 * {@link import("../admin/admin-page-header").AdminPageHeader} and the admin
 * welcome cards — the same `glass-panel-strong` square with `shadow-glow` — so a
 * section heading inside a page reads as a quieter echo of the page heading
 * above it rather than as a new shape. Pages that stack several of these get
 * their structure from the headings instead of from bare dividers.
 */
export function SectionCard({ icon, title, children, className }: SectionCardProps) {
  const cls = ["flex flex-col gap-5 rounded-2xl glass-panel-strong p-6", className]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={cls}>
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl glass-panel-strong text-accent shadow-glow">
          <AnimatedIcon icon={icon} animation="spin-occasional" size={20} />
        </span>
        <h2 className="min-w-0 truncate font-display text-lg font-semibold tracking-tight text-on-surface">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}
