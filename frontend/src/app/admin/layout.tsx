"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV = [
  { href: "/admin/agent-skills", label: "Agent Skills" },
  { href: "/admin/workflows", label: "Workflows" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden">
      <nav className="relative flex w-64 shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl">
        <div className="flex items-center gap-3 border-b border-glass-border px-5 py-4">
          <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow" />
          <span className="text-sm font-semibold tracking-tight text-gradient-accent">
            A2Flow Admin
          </span>
        </div>
        <ul className="flex flex-col gap-1 px-3 py-3">
          {NAV.map((item) => {
            const isActive = pathname?.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={[
                    "relative block rounded-xl px-3 py-2 text-sm transition-all duration-150",
                    isActive
                      ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                      : "text-on-surface-variant hover:bg-glass hover:text-on-surface",
                  ].join(" ")}
                >
                  {isActive && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-1/2 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-glow"
                    />
                  )}
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="mt-auto flex items-center justify-between gap-2 border-t border-glass-border px-4 py-4">
          <Link
            href="/"
            className="text-xs text-on-surface-variant transition-colors hover:text-accent"
          >
            ← Back to chat
          </Link>
          <ThemeToggle />
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
