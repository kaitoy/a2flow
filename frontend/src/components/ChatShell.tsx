"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { AppHeader } from "./AppHeader";
import { SessionList } from "./SessionList";
import { ErrorBanner } from "./ui/error-banner";

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
        <AppHeader />

        {error && (
          <div className="shrink-0 mx-4 mt-3">
            <ErrorBanner error={error} onDismiss={() => dispatch(clearError())} />
          </div>
        )}

        {children}
      </div>
    </div>
  );
}
