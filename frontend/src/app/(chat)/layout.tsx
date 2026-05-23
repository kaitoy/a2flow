/**
 * @module ChatLayout — Persistent layout that wraps all chat routes (`/sessions/[id]`
 * and `/new-session`) with the shared shell so the sidebar and header are not
 * remounted on session switches.
 */
import { ChatShell } from "@/components/ChatShell";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <ChatShell>{children}</ChatShell>;
}
