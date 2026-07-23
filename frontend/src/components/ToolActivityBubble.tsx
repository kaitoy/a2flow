"use client";

import type { ToolCallActivityContent } from "@/lib/agentActivity";
import { Badge } from "./ui/badge";
import { Spinner } from "./ui/spinner";

/**
 * Render a compact, left-aligned status line for a single agent tool call,
 * transitioning from a spinner while `running` to a check mark once `done`.
 * While running, the pill carries the signature live edge (accent light
 * circling its border — static accent ring under prefers-reduced-motion),
 * and the tool name renders in the mono data face.
 */
export function ToolActivityBubble({ content }: { content: ToolCallActivityContent }) {
  const running = content.status === "running";
  return (
    <div className="mb-2 flex justify-start animate-message-in">
      <div
        className={[
          "inline-flex items-center gap-2 rounded-full px-3 py-1.5",
          "text-xs leading-none glass-panel text-on-surface-variant",
          running ? "live-edge" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {running ? (
          <Spinner size="sm" />
        ) : (
          <span className="text-accent" aria-hidden>
            ✓
          </span>
        )}
        <span className="font-mono font-medium text-on-surface">{content.name}</span>
        {content.isMcp && <Badge>MCP</Badge>}
        <span>{running ? "running…" : "done"}</span>
      </div>
    </div>
  );
}
