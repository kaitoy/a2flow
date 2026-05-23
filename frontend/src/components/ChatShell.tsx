"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback } from "react";
import logo from "@/../assets/logo.png";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
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
  const userId = useAppSelector((s) => s.chat.userId);
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
          <ThemeToggle />
        </header>

        {error && (
          <div className="shrink-0 mx-4 mt-3 flex items-center justify-between gap-3 rounded-xl border border-error/40 bg-error-container px-4 py-2 text-sm text-on-error-container backdrop-blur-md">
            <span className="flex items-center gap-2">
              <span aria-hidden="true">⚠</span>
              {error}
            </span>
            <button
              type="button"
              onClick={() => dispatch(clearError())}
              className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-colors hover:bg-error/15 hover:text-on-error-container"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        {children}
      </div>
    </div>
  );
}
