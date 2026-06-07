/**
 * @module ChatLayout — Persistent layout that wraps all chat routes (`/sessions/[id]`
 * and `/new-session`) with the shared shell so the sidebar and header are not
 * remounted on session switches.
 */
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatShell } from "@/components/ChatShell";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ChatShell>{children}</ChatShell>
    </AuthProvider>
  );
}
