"use client";

import type { ToolCallActivityContent } from "@/lib/agentActivity";
import { Spinner } from "./ui/spinner";

/**
 * Render a compact, left-aligned status line for a single agent tool call,
 * transitioning from a spinner while `running` to a check mark once `done`.
 */
export function ToolActivityBubble({ content }: { content: ToolCallActivityContent }) {
  const running = content.status === "running";
  return (
    <div className="mb-2 flex justify-start animate-message-in">
      <div
        className={[
          "inline-flex items-center gap-2 rounded-full px-3 py-1.5",
          "text-xs leading-none glass-panel text-on-surface-variant",
        ].join(" ")}
      >
        {running ? (
          <Spinner size="sm" />
        ) : (
          <span className="text-accent" aria-hidden>
            ✓
          </span>
        )}
        <span className="font-medium text-on-surface">{content.name}</span>
        {content.isMcp && (
          <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] tracking-wide uppercase text-accent">
            MCP
          </span>
        )}
        <span>{running ? "running…" : "done"}</span>
      </div>
    </div>
  );
}
