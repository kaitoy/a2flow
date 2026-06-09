"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback } from "react";
import logo from "@/../assets/logo.png";
import { LogoutButton } from "@/components/auth/logout-button";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { NotificationBell } from "./NotificationBell";
import { SessionList } from "./SessionList";
import { ThemeToggle } from "./ThemeToggle";

/**
 * Persistent shell for chat routes: sidebar with session list, header with logo,
 * and shared error banner. Children render the active session's conversation panel.
 *
 * Lives in a route layout so it is preserved across navigations between sessions —
 * switching sessions does not remount this tree, so the session list is fetched once
 * and the logo image is loaded once per page load.
 */
export function ChatShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const userId = useAppSelector((s) => s.auth.user?.id ?? "");
  const sessionId = useAppSelector((s) => s.chat.sessionId);
  const isRunning = useAppSelector((s) => s.chat.isRunning);
  const error = useAppSelector((s) => s.chat.error);

  const switchSession = useCallback(
    (target: string) => {
      if (isRunning) return;
      router.push(`/sessions/${target}`);
    },
    [isRunning, router]
  );

  const newSession = useCallback(() => {
    if (isRunning) return;
    router.push("/new-session");
  }, [isRunning, router]);

  const onSessionDeleted = useCallback(
    (deletedId: string) => {
      if (deletedId === sessionId) router.push("/new-session");
    },
    [sessionId, router]
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <SessionList
        userId={userId}
        currentSessionId={sessionId}
        onSelect={switchSession}
        onNew={newSession}
        onDeleted={onSessionDeleted}
        disabled={isRunning}
      />

      <div className="flex flex-col flex-1 min-w-0">
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

        <ChatErrorBanner error={error} onDismiss={() => dispatch(clearError())} />

        {children}
      </div>
    </div>
  );
}
