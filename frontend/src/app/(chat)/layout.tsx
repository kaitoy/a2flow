/**
 * @module ChatLayout — Persistent layout that wraps all chat routes (`/sessions/[id]`
 * and `/sessions/new`) with the shared shell so the sidebar and header are not
 * remounted on session switches. Restricted to `super_admin`: everyone else sees
 * an access-denied screen instead of the chat shell.
 */
"use client";

import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatShell } from "@/components/ChatShell";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Role, useHasRole } from "@/lib/roles";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ChatAccessGate>{children}</ChatAccessGate>
    </AuthProvider>
  );
}

/**
 * Blocks non-`super_admin` users from the chat shell (and its `listSessions()`
 * call) before it ever mounts. `AuthProvider` guarantees the auth slice is
 * already resolved by the time this renders.
 */
function ChatAccessGate({ children }: { children: React.ReactNode }) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  if (!isSuperAdmin) {
    return <AccessDeniedState fill="screen" />;
  }
  return <ChatShell>{children}</ChatShell>;
}
