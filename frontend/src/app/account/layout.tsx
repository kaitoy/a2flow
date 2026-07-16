/** @module AccountLayout — Auth-gated shell for the self-service account pages. */
"use client";

import { AppHeader } from "@/components/AppHeader";
import { AuthProvider } from "@/components/auth/auth-provider";

/**
 * Shell for the signed-in user's account pages. Reuses the shared
 * {@link AuthProvider} (so children render only once authenticated) and the
 * shared {@link AppHeader}, with a scrollable centered content area below it.
 *
 * @param props.children - The account page content to render.
 */
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppHeader />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </AuthProvider>
  );
}
