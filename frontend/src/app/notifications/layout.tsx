/** @module NotificationsLayout — Auth-gated shell for the signed-in user's notifications page. */
"use client";

import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";

/**
 * Shell for the signed-in user's notifications page. Reuses the shared
 * {@link AuthProvider} (so children render only once authenticated) and the
 * shared {@link AppHeader}, with a scrollable centered content area below it.
 *
 * @param props.children - The notifications page content to render.
 */
export default function NotificationsLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppHeader />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </AuthProvider>
  );
}
