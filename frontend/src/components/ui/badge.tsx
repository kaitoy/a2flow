import type { ReactNode } from "react";

/**
 * Small accent pill for tags and status labels (e.g. a role indicator or an
 * MCP tool tag). Renders in the mono `text-badge` data face per DESIGN.md.
 */
export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-badge tracking-wide uppercase text-accent">
      {children}
    </span>
  );
}
