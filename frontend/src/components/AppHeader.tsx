/** @module AppHeader — Shared top bar with logo, title, and account actions. */
"use client";

import Image from "next/image";
import logo from "@/../assets/logo.png";
import { LogoutButton } from "@/components/auth/logout-button";
import { NotificationBell } from "@/components/NotificationBell";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * Application top bar shared by the chat and admin shells. Renders the A2Flow
 * logo and title on the left and the notification, logout, and theme controls
 * on the right.
 */
export function AppHeader() {
  return (
    <header className="shrink-0 flex items-center justify-between px-6 py-3 border-b border-glass-border bg-glass backdrop-blur-xl">
      <div className="flex items-center gap-3">
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
      </div>
      <div className="flex items-center gap-2">
        <NotificationBell />
        <LogoutButton />
        <ThemeToggle />
      </div>
    </header>
  );
}
