"use client";

import { ChatPanelSkeleton } from "@/components/ChatPanelSkeleton";
import { useT } from "@/i18n/provider";

/**
 * Route loading fallback for `/sessions/new` and `/sessions/[sessionId]`.
 * Renders inside `ChatShell` (the `(chat)` layout), so the sidebar/header
 * chrome stays mounted — this only covers the conversation panel.
 */
export default function Loading() {
  const t = useT();
  return (
    <div role="status" aria-label={t("common.loading")} className="flex flex-1 flex-col min-h-0">
      <ChatPanelSkeleton />
    </div>
  );
}
