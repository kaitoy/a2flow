/**
 * @module AdminLayout — Admin section shell with a collapsible sidebar
 * navigation and theme toggle. The sidebar can be toggled between a full-width
 * labelled list and a narrow icon-only rail (with hover tooltips), mirroring the
 * collapse behavior of the workflow execution task timeline. On mobile the
 * sidebar hides and opens instead as an off-canvas drawer from the header's
 * hamburger button.
 */
"use client";

import { ChevronLeft, ExternalLink, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";
import { SidebarDrawer } from "@/components/ui/sidebar-drawer";
import { SlidingIndicator } from "@/components/ui/sliding-indicator";
import { Tooltip } from "@/components/ui/tooltip";
import { useVisibleAdminNavItems } from "@/lib/admin-nav";
import { Role, useHasRole } from "@/lib/roles";

/**
 * The admin section's navigation link list, shared by the static desktop
 * sidebar and the mobile drawer so the two can't drift apart. Owns its own
 * item-ref map so each instance's sliding active indicator tracks its own DOM.
 */
function AdminNavList({
  collapsed,
  onNavigate,
}: {
  /** Whether to render the icon-only rail variant (desktop collapse). */
  collapsed: boolean;
  /** Called after a link is activated (the drawer closes itself with this). */
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());
  const navItems = useVisibleAdminNavItems();
  const activeKey = navItems.find((n) => pathname?.startsWith(n.href))?.href ?? null;

  return (
    <ul className="relative flex flex-col gap-1 px-3 py-3">
      {navItems.map((item) => {
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
                  onClick={onNavigate}
                  className={[
                    "relative block rounded-xl px-3 py-2 text-sm transition-all duration-150",
                    isActive
                      ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_var(--inner-top-highlight)]"
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
  );
}

/**
 * Bottom-pinned link to the interactive API reference (`/api-doc`), opened in
 * a new tab. Visible only to admins and super admins (super_admin bypasses via
 * {@link useHasRole}, mirroring every role-gated entry in `adminNavItems`).
 * Kept out of `adminNavItems` deliberately: it isn't a route this section
 * navigates into (no active-state highlighting applies) and must not appear
 * among the welcome page's quick-action cards.
 */
function AdminNavFooter({
  collapsed,
  onNavigate,
}: {
  /** Whether to render the icon-only rail variant (desktop collapse). */
  collapsed: boolean;
  /** Called after the link is activated (the drawer closes itself with this). */
  onNavigate?: () => void;
}) {
  const canViewApiDocs = useHasRole(Role.ADMIN);
  if (!canViewApiDocs) return null;

  return (
    <div className="mt-auto px-3 py-3">
      <Tooltip label="API Docs" placement="right" disabled={!collapsed}>
        <span className="block">
          <a
            href="/api-doc"
            target="_blank"
            rel="noreferrer"
            onClick={onNavigate}
            className="relative block rounded-xl px-3 py-2 text-sm text-on-surface-variant transition-all duration-150 hover:bg-glass hover:text-on-surface"
          >
            <span
              className={["flex items-center gap-2.5", collapsed ? "justify-center" : ""].join(" ")}
            >
              <ExternalLink size={18} strokeWidth={1.8} aria-hidden="true" className="shrink-0" />
              {!collapsed && "API Docs"}
            </span>
          </a>
        </span>
      </Tooltip>
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  return (
    <AuthProvider>
      <div className="flex h-dvh overflow-hidden">
        <nav
          className={[
            "relative max-md:hidden flex shrink-0 flex-col border-r border-glass-border glass-chrome",
            collapsed ? "w-16" : "w-64",
          ].join(" ")}
        >
          <div
            className={[
              "flex h-16 items-center px-3",
              collapsed ? "justify-center" : "justify-end",
            ].join(" ")}
          >
            <button
              type="button"
              onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
              className="cursor-pointer rounded-lg p-1.5 pointer-coarse:p-2.5 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
            >
              {collapsed ? (
                <Menu size={20} strokeWidth={1.8} aria-hidden="true" />
              ) : (
                <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
              )}
            </button>
          </div>
          <AdminNavList collapsed={collapsed} />
          <AdminNavFooter collapsed={collapsed} />
        </nav>
        <SidebarDrawer open={drawerOpen} onClose={closeDrawer} label="Admin navigation">
          <nav className="flex w-64 flex-col border-r border-glass-border glass-chrome pt-3">
            <AdminNavList collapsed={false} onNavigate={closeDrawer} />
            <AdminNavFooter collapsed={false} onNavigate={closeDrawer} />
          </nav>
        </SidebarDrawer>
        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader onMenuClick={() => setDrawerOpen(true)} />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </AuthProvider>
  );
}
