"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import type { ToolCallActivityContent } from "@/lib/agentActivity";
import { Badge } from "./ui/badge";
import { Spinner } from "./ui/spinner";

/**
 * Render one value of a tool call — its arguments or its result — as pretty
 * printed JSON. A value that is already a string is shown as-is rather than
 * re-quoted, so a plain-text tool answer stays readable.
 *
 * @param value - The parsed value to display.
 * @returns The text to render inside the detail panel.
 */
function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** One labelled JSON block inside the expanded detail panel. */
function DetailBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-label-caps text-on-surface-variant">{label}</span>
      <pre className="max-h-64 overflow-auto rounded-lg bg-surface-container-high px-3 py-2 font-mono text-xs leading-relaxed text-on-surface">
        {formatValue(value)}
      </pre>
    </div>
  );
}

/**
 * Render a compact, left-aligned status line for a single agent tool call,
 * transitioning from a spinner while `running` to a check mark once `done`.
 * While running, the pill carries the signature live edge (accent light
 * circling its border — static accent ring under prefers-reduced-motion),
 * and the tool name renders in the mono data face.
 *
 * Once the call has arguments or a result, the pill becomes a disclosure
 * button: expanding it shows what the tool was called with and what came back,
 * which is the only place a mocked call's details can be inspected — a stub
 * never reaches the MCP proxy, so it leaves no audit row behind.
 */
export function ToolActivityBubble({ content }: { content: ToolCallActivityContent }) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  const running = content.status === "running";
  const hasDetails = content.args !== undefined || content.result !== undefined;

  const pill = (
    <>
      {running ? (
        <Spinner size="sm" />
      ) : (
        <span className="text-accent" aria-hidden>
          ✓
        </span>
      )}
      <span className="font-mono font-medium text-on-surface">{content.name}</span>
      {content.isMcp && <Badge>MCP</Badge>}
      {content.mocked && <Badge>Mocked</Badge>}
      <span>{running ? "running…" : "done"}</span>
      {hasDetails && (
        <ChevronDown
          size={14}
          strokeWidth={2}
          aria-hidden
          className={[
            "text-on-surface-variant transition-transform duration-200",
            expanded ? "rotate-180" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        />
      )}
    </>
  );

  const pillClass = [
    "inline-flex items-center gap-2 rounded-full px-3 py-1.5",
    "text-xs leading-none glass-panel text-on-surface-variant",
    running ? "live-edge" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="mb-2 flex flex-col items-start gap-1.5 animate-message-in">
      {hasDetails ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => setExpanded((open) => !open)}
          className={`${pillClass} cursor-pointer transition-colors hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50`}
        >
          {pill}
        </button>
      ) : (
        <div className={pillClass}>{pill}</div>
      )}
      {hasDetails && expanded && (
        <div
          id={panelId}
          className="flex w-full max-w-[75%] flex-col gap-3 rounded-2xl glass-panel px-4 py-3"
        >
          {content.args !== undefined && <DetailBlock label="Arguments" value={content.args} />}
          {content.result !== undefined && <DetailBlock label="Result" value={content.result} />}
        </div>
      )}
    </div>
  );
}
