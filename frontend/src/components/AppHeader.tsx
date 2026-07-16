/** @module AppHeader — Shared top bar with logo, title, and account actions. */
"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import logo from "@/../assets/logo.png";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { UserProfileButton } from "@/components/UserProfileButton";

/** Props for {@link AppHeader}. */
export interface AppHeaderProps {
  /**
   * Optional contextual content rendered beside the logo/title (e.g. a workflow
   * name). Used by standalone screens that have no list shell of their own to
   * convey which record is being viewed.
   */
  children?: ReactNode;
  /**
   * When provided, renders a hamburger button (visible only below the `md`
   * breakpoint) that shells use to open their sidebar as a mobile drawer.
   */
  onMenuClick?: () => void;
}

/**
 * Application top bar shared by the chat, admin, and standalone shells. Renders
 * the A2Flow logo and title (linking to the welcome page) on the left and the
 * notification, theme, and account profile controls on the right. Any
 * `children` render next to the title as contextual content. Shells with a
 * sidebar pass `onMenuClick` to expose it as a drawer on mobile.
 */
export function AppHeader({ children, onMenuClick }: AppHeaderProps) {
  return (
    <header className="shrink-0 flex h-16 items-center justify-between px-4 sm:px-6 border-b border-glass-border glass-chrome">
      <div className="flex min-w-0 items-center gap-3">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            aria-label="Open menu"
            aria-haspopup="dialog"
            className="md:hidden -ml-1 shrink-0 cursor-pointer rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
          >
            <Menu size={20} strokeWidth={1.8} aria-hidden="true" />
          </button>
        )}
        <Link
          href="/admin"
          aria-label="A2Flow home"
          className={[
            "flex items-center gap-3 rounded-xl",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
          ].join(" ")}
        >
          <Image
            src={logo}
            alt="A2Flow logo"
            width={logo.width}
            height={logo.height}
            className="h-10 w-auto"
            priority
          />
          <h1 className="font-display text-[22px] leading-[32px] font-semibold tracking-tight text-gradient-accent">
            A2Flow
          </h1>
        </Link>
        {children}
      </div>
      <div className="flex items-center gap-2">
        <NotificationBell />
        <ThemeToggle />
        <UserProfileButton />
      </div>
    </header>
  );
}
