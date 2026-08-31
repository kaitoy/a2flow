/**
 * @module ToolOutputFormatPanel — What the chosen tool says it returns.
 *
 * Sits directly under the tool picker on the tool-mock form, above the response
 * editor, because the operator is about to type a JSON object standing in for
 * this tool's result and has otherwise nothing to write it against.
 *
 * It reports only what the tool itself declares. Plenty of MCP servers predate
 * the spec revision that added an output schema, and those are shown saying so
 * rather than being given a made-up shape — the input schema is not a substitute
 * and is deliberately not offered here.
 *
 * Reading that declaration means connecting to the server live, which a `stdio`
 * server can take a minute to answer, so the panel holds the space with a
 * skeleton in the meantime rather than appearing out of nowhere once the reply
 * lands.
 */
"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { JsonBlock } from "@/components/ui/json-block";
import { Skeleton } from "@/components/ui/skeleton";

/** Props for {@link ToolOutputFormatPanel}. */
export interface ToolOutputFormatPanelProps {
  /** The chosen tool. Nothing renders while this is empty. */
  toolName: string;
  /** The tool's own description, when it advertises one. */
  description?: string | null;
  /** JSON Schema of the tool's structured result, or nullish when undeclared. */
  outputSchema?: Record<string, unknown> | null;
  /**
   * The tool is chosen but its declaration has not arrived yet, so the body is
   * a skeleton and `description` / `outputSchema` are ignored. Distinct from a
   * tool that has answered and declares no output format.
   */
  loading?: boolean;
}

/** The body shown while the tool's declaration is still in flight. */
function OutputFormatSkeleton({ id }: { id: string }) {
  return (
    <div
      id={id}
      role="status"
      aria-busy="true"
      aria-label="Loading output format"
      className="flex flex-col gap-2 rounded-xl glass-panel px-4 py-3"
    >
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-32 w-full rounded-lg" />
    </div>
  );
}

/**
 * A collapsible panel describing one tool's declared output.
 *
 * Open by default — it is reference material for the field below it, and
 * {@link JsonBlock} caps its own height, so an open panel cannot push the
 * response editor off screen.
 *
 * @param props - The tool to describe.
 * @returns The rendered panel, or nothing when no tool is chosen.
 */
export function ToolOutputFormatPanel({
  toolName,
  description,
  outputSchema,
  loading = false,
}: ToolOutputFormatPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const panelId = useId();

  if (toolName === "") return null;

  const hasSchema = outputSchema !== null && outputSchema !== undefined;

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((open) => !open)}
        className="inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-lg py-1 text-label-caps text-on-surface-variant transition-colors hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <ChevronDown
          size={14}
          strokeWidth={1.8}
          aria-hidden="true"
          className={`transition-transform${expanded ? " rotate-180" : ""}`}
        />
        Output format
        <span className="font-mono text-xs normal-case tracking-normal">{toolName}</span>
      </button>
      {expanded &&
        (loading ? (
          <OutputFormatSkeleton id={panelId} />
        ) : (
          <div id={panelId} className="flex flex-col gap-2 rounded-xl glass-panel px-4 py-3">
            {description ? (
              <p className="whitespace-pre-wrap text-sm text-on-surface-variant">{description}</p>
            ) : null}
            {hasSchema ? (
              <JsonBlock value={outputSchema} />
            ) : (
              <p className="text-xs text-on-surface-variant">
                This tool does not declare an output format, so there is no shape to follow. Write
                whatever the workflow needs to read back.
              </p>
            )}
          </div>
        ))}
    </div>
  );
}
