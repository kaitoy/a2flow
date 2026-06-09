/** @module AdminLayout — Admin section shell with sidebar navigation and theme toggle. */
"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";
import logo from "@/../assets/logo.png";
import { AuthProvider } from "@/components/auth/auth-provider";
import { LogoutButton } from "@/components/auth/logout-button";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { SlidingIndicator } from "@/components/ui/sliding-indicator";

const NAV = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/agent-skills", label: "Agent Skills" },
  { href: "/admin/workflows", label: "Workflows" },
  { href: "/admin/workflow-sessions", label: "Workflow Sessions" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  const activeKey = NAV.find((n) => pathname?.startsWith(n.href))?.href ?? null;

  return (
    <AuthProvider>
      <div className="flex h-screen overflow-hidden">
        <nav className="relative flex w-64 shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl">
          <div className="flex items-center gap-3 border-b border-glass-border px-5 py-4">
            <Image
              src={logo}
              alt="A2Flow logo"
              width={logo.width}
              height={logo.height}
              className="h-9 w-auto"
              priority
            />
            <span
              className="text-base font-semibold tracking-tight text-gradient-accent"
              style={{ fontFamily: "var(--font-space-grotesk)" }}
            >
              A2Flow
            </span>
          </div>
          <ul className="relative flex flex-col gap-1 px-3 py-3">
            {NAV.map((item) => {
              const isActive = pathname?.startsWith(item.href);
              return (
                <li
                  key={item.href}
                  ref={(el) => {
                    if (el) itemMap.current.set(item.href, el);
                    else itemMap.current.delete(item.href);
                  }}
                >
                  <Link
                    href={item.href}
                    className={[
                      "relative block rounded-xl px-3 py-2 text-sm transition-all duration-150",
                      isActive
                        ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                        : "text-on-surface-variant hover:bg-glass hover:text-on-surface",
                    ].join(" ")}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
            <SlidingIndicator itemMap={itemMap} activeKey={activeKey} deps={[pathname]} />
          </ul>
          <div className="mt-auto flex items-center justify-between gap-2 border-t border-glass-border px-4 py-4">
            <Link
              href="/"
              className="text-xs text-on-surface-variant transition-colors hover:text-accent"
            >
              ← Back to chat
            </Link>
            <NotificationBell />
            <LogoutButton className="text-xs" />
            <ThemeToggle />
          </div>
        </nav>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </AuthProvider>
  );
}
