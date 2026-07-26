/** @module ProfileLayout — Auth-gated shell for the signed-in user's profile pages. */
"use client";

import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";

/**
 * Shell for the signed-in user's profile pages. Reuses the shared
 * {@link AuthProvider} (so children render only once authenticated) and the
 * shared {@link AppHeader}, with a scrollable centered content area below it.
 *
 * @param props.children - The profile page content to render.
 */
export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppHeader />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </AuthProvider>
  );
}
