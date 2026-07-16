"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { AppHeader } from "./AppHeader";
import { SessionList } from "./SessionList";
import { ErrorBanner } from "./ui/error-banner";
import { SidebarDrawer } from "./ui/sidebar-drawer";

/**
 * Persistent shell for chat routes: sidebar with session list, header with logo,
 * and shared error banner. Children render the active session's conversation panel.
 * On mobile the session list hides and is reachable instead through the header's
 * hamburger button, which opens it as an off-canvas drawer.
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
  const [drawerOpen, setDrawerOpen] = useState(false);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const switchSession = useCallback(
    (target: string) => {
      if (isRunning) return;
      setDrawerOpen(false);
      router.push(`/sessions/${target}`);
    },
    [isRunning, router]
  );

  const newSession = useCallback(() => {
    if (isRunning) return;
    setDrawerOpen(false);
    router.push("/sessions/new");
  }, [isRunning, router]);

  const onSessionDeleted = useCallback(
    (deletedId: string) => {
      if (deletedId === sessionId) router.push("/sessions/new");
    },
    [sessionId, router]
  );

  const sessionListProps = {
    userId,
    currentSessionId: sessionId,
    onSelect: switchSession,
    onNew: newSession,
    onDeleted: onSessionDeleted,
    disabled: isRunning,
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <SessionList {...sessionListProps} className="max-md:hidden" />
      <SidebarDrawer open={drawerOpen} onClose={closeDrawer} label="Chat sessions">
        <SessionList {...sessionListProps} />
      </SidebarDrawer>

      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader onMenuClick={() => setDrawerOpen(true)} />

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
