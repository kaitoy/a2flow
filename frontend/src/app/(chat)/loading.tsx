import { ChatPanelSkeleton } from "@/components/ChatPanelSkeleton";

/**
 * Route loading fallback for `/sessions/new` and `/sessions/[sessionId]`.
 * Renders inside `ChatShell` (the `(chat)` layout), so the sidebar/header
 * chrome stays mounted — this only covers the conversation panel.
 */
export default function Loading() {
  return (
    <div role="status" aria-label="Loading" className="flex flex-1 flex-col min-h-0">
      <ChatPanelSkeleton />
    </div>
  );
}
