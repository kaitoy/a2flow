/** @module ConsultationNotice — the bar a workflow session shows while it waits on an approval. */
"use client";

import { MessageCircleQuestion } from "lucide-react";
import { useT } from "@/i18n/provider";

/**
 * Notice above the chat input of a session that is `waiting_for_approval`.
 *
 * The waiting session takes no messages, so the page sends what is typed below
 * it to a consultation instead: a side session, shown in its own tab, where the
 * run's participants can ask the agent — and each other — about the request
 * before it is decided. Its agent can read the linked knowledge bases and the
 * run's own records, but calls no MCP server tool and changes nothing, and
 * the decision closes it. This bar says so, so nobody expects the question to
 * steer the run.
 */
export function ConsultationNotice() {
  const t = useT();
  return (
    <div
      className="flex items-start gap-2 rounded-xl glass-panel px-4 py-3 text-sm text-on-surface animate-message-in"
      role="status"
    >
      <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
      <span>{t("app.thisSessionIsWaitingForAnApproval")}</span>
    </div>
  );
}
