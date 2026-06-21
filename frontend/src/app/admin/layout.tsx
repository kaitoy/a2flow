/** @module AdminLayout — Admin section shell with sidebar navigation and theme toggle. */
"use client";

import { CheckCircle2, ListChecks, Server, Users, Wand2, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";
import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";
import { SlidingIndicator } from "@/components/ui/sliding-indicator";

const NAV = [
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/agent-skills", label: "Agent Skills", icon: Wand2 },
  { href: "/admin/mcp-servers", label: "MCP Servers", icon: Server },
  { href: "/admin/workflows", label: "Workflows", icon: Workflow },
  { href: "/admin/workflow-sessions", label: "Workflow Sessions", icon: ListChecks },
  { href: "/admin/approvals", label: "Approvals", icon: CheckCircle2 },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  const activeKey = NAV.find((n) => pathname?.startsWith(n.href))?.href ?? null;

  return (
    <AuthProvider>
      <div className="flex h-screen overflow-hidden">
        <nav className="relative flex w-64 shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl">
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
                    <span className="flex items-center gap-2.5">
                      <item.icon
                        size={18}
                        strokeWidth={1.8}
                        aria-hidden="true"
                        className="shrink-0"
                      />
                      {item.label}
                    </span>
                  </Link>
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
