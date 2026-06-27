/** @module AppHeader — Shared top bar with logo, title, and account actions. */
"use client";

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
}

/**
 * Application top bar shared by the chat, admin, and standalone shells. Renders
 * the A2Flow logo and title (linking to the welcome page) on the left and the
 * notification, theme, and account profile controls on the right. Any
 * `children` render next to the title as contextual content.
 */
export function AppHeader({ children }: AppHeaderProps) {
  return (
    <header className="shrink-0 flex h-16 items-center justify-between px-6 border-b border-glass-border bg-glass backdrop-blur-xl">
      <div className="flex min-w-0 items-center gap-3">
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
          <h1
            className="text-[22px] leading-[32px] font-semibold tracking-tight text-gradient-accent"
            style={{ fontFamily: "var(--font-space-grotesk)" }}
          >
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
