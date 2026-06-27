/**
 * @module AdminLayout — Admin section shell with a collapsible sidebar
 * navigation and theme toggle. The sidebar can be toggled between a full-width
 * labelled list and a narrow icon-only rail (with hover tooltips), mirroring the
 * collapse behavior of the workflow session task timeline.
 */
"use client";

import { ChevronLeft, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";
import { SlidingIndicator } from "@/components/ui/sliding-indicator";
import { Tooltip } from "@/components/ui/tooltip";
import { adminNavItems } from "@/lib/admin-nav";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  const activeKey = adminNavItems.find((n) => pathname?.startsWith(n.href))?.href ?? null;
  const [collapsed, setCollapsed] = useState(false);

  return (
    <AuthProvider>
      <div className="flex h-screen overflow-hidden">
        <nav
          className={[
            "relative flex shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl",
            collapsed ? "w-16" : "w-64",
          ].join(" ")}
        >
          <div
            className={[
              "flex h-16 items-center border-b border-glass-border px-3",
              collapsed ? "justify-center" : "justify-end",
            ].join(" ")}
          >
            <button
              type="button"
              onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
              className="rounded-lg p-1.5 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
            >
              {collapsed ? (
                <Menu size={20} strokeWidth={1.8} aria-hidden="true" />
              ) : (
                <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              )}
            </button>
          </div>
          <ul className="relative flex flex-col gap-1 px-3 py-3">
            {adminNavItems.map((item) => {
              const isActive = pathname?.startsWith(item.href);
              return (
                <li
                  key={item.href}
                  ref={(el) => {
                    if (el) itemMap.current.set(item.href, el);
                    else itemMap.current.delete(item.href);
                  }}
                >
                  <Tooltip label={item.label} placement="right" disabled={!collapsed}>
                    <span className="block">
                      <Link
                        href={item.href}
                        className={[
                          "relative block rounded-xl px-3 py-2 text-sm transition-all duration-150",
                          isActive
                            ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                            : "text-on-surface-variant hover:bg-glass hover:text-on-surface",
                        ].join(" ")}
                      >
                        <span
                          className={[
                            "flex items-center gap-2.5",
                            collapsed ? "justify-center" : "",
                          ].join(" ")}
                        >
                          <item.icon
                            size={18}
                            strokeWidth={1.8}
                            aria-hidden="true"
                            className="shrink-0"
                          />
                          {!collapsed && item.label}
                        </span>
                      </Link>
                    </span>
                  </Tooltip>
                </li>
              );
            })}
            <SlidingIndicator itemMap={itemMap} activeKey={activeKey} deps={[pathname]} />
          </ul>
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </AuthProvider>
  );
}
