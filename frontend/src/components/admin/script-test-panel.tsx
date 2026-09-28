/**
 * @module ScriptTestPanel — Try a script MCP server's tools from its form,
 * before the server is saved.
 *
 * Both actions launch the script exactly as the saved server would be, using
 * what the form holds right now — language, source, and environment
 * variables. A script that cannot load is reported with its traceback instead
 * of a list of tools, which is what makes a broken script visible here rather
 * than as an unreachable server once an agent tries to use it.
 */
"use client";

import { useState } from "react";
import { type Control, useWatch } from "react-hook-form";
import { FormField } from "@/components/admin/form-field";
import { pairsToRecord } from "@/components/admin/key-value-editor";
import type { McpServerFormValues } from "@/components/admin/mcp-server-fields";
import { nonEmpty } from "@/components/admin/string-list-editor";
import { Button } from "@/components/ui/button";
import { JsonBlock } from "@/components/ui/json-block";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  callScriptTool,
  getApiErrorMessage,
  listScriptTools,
  type McpToolInfo,
  type ScriptCallResult,
} from "@/lib/api";

/** Props for {@link ScriptTestPanel}. */
export interface ScriptTestPanelProps {
  /** `control` from the page's `useForm`, read for the script under test. */
  control: Control<McpServerFormValues>;
}

/**
 * Build an arguments skeleton for a tool: every property its input schema
 * declares, set to `null` for the author to fill in.
 *
 * @param tool - The tool to build arguments for.
 * @returns Pretty-printed JSON, `{}` when the schema declares no properties.
 */
export function argumentsTemplate(tool: McpToolInfo | undefined): string {
  const properties = tool?.inputSchema?.properties;
  const names =
    properties && typeof properties === "object" ? Object.keys(properties as object) : [];
  return JSON.stringify(Object.fromEntries(names.map((name) => [name, null])), null, 2);
}

/**
 * Parse the arguments textarea into the object a tool call takes.
 *
 * @param text - The textarea's contents.
 * @returns The object, or an error message when it is not a JSON object.
 */
function parseArguments(text: string): { value: Record<string, unknown> } | { error: string } {
  let value: unknown;
  try {
    value = JSON.parse(text.trim() || "{}");
  } catch (err) {
    return { error: `Invalid JSON: ${(err as Error).message}` };
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return { error: "Arguments must be a JSON object." };
  }
  return { value: value as Record<string, unknown> };
}

/**
 * Test run for a script server: **Load tools** launches the unsaved script and
 * lists its tools (or shows why it failed to load); picking a tool fills an
 * arguments skeleton, and **Run** calls it and shows the result under **Output**.
 */
export function ScriptTestPanel({ control }: ScriptTestPanelProps) {
  const [language, source, packages, env] = useWatch({
    control,
    name: ["language", "source", "packages", "env"],
  });
  const loadAction = useAsyncAction({ showDone: false });
  const runAction = useAsyncAction({ showDone: false });
  const [tools, setTools] = useState<McpToolInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toolName, setToolName] = useState("");
  const [argsText, setArgsText] = useState("{}");
  const [argsError, setArgsError] = useState<string | null>(null);
  const [result, setResult] = useState<ScriptCallResult | null>(null);

  const script = () => ({
    language,
    source,
    packages: nonEmpty(packages),
    env: pairsToRecord(env),
  });

  function selectTool(name: string, from: McpToolInfo[]) {
    setToolName(name);
    setArgsText(argumentsTemplate(from.find((tool) => tool.name === name)));
    setArgsError(null);
    setResult(null);
  }

  async function handleLoad() {
    setLoadError(null);
    setResult(null);
    try {
      const loaded = await loadAction.run(() => listScriptTools(script()));
      const found = loaded.tools ?? [];
      setTools(loaded.error ? null : found);
      setLoadError(loaded.error ?? null);
      selectTool(found[0]?.name ?? "", found);
    } catch (err) {
      setTools(null);
      setLoadError(getApiErrorMessage(err));
    }
  }

  async function handleRun() {
    const parsed = parseArguments(argsText);
    if ("error" in parsed) {
      setArgsError(parsed.error);
      return;
    }
    setArgsError(null);
    try {
      setResult(
        await runAction.run(() =>
          callScriptTool({ ...script(), toolName, arguments: parsed.value })
        )
      );
    } catch (err) {
      setResult({ isError: true, content: [getApiErrorMessage(err)] });
    }
  }

  return (
    <FormField htmlFor="script-test" label="Test Run">
      <div className="flex flex-col gap-3 rounded-xl glass-panel p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-on-surface-variant">
            Runs the source, packages, and environment variables above, without saving them.
          </p>
          <Button
            variant="secondary"
            onClick={handleLoad}
            disabled={loadAction.inFlight || !source.trim()}
            status={loadAction.status}
            pendingLabel="Loading…"
          >
            Load tools
          </Button>
        </div>

        {loadError && <JsonBlock value={loadError} tone="error" />}

        {tools !== null &&
          (tools.length === 0 ? (
            <p className="text-sm text-on-surface-variant">This script exposes no tools.</p>
          ) : (
            <>
              <FormField htmlFor="script-test-tool" label="Tool">
                <Select
                  id="script-test-tool"
                  options={tools.map((tool) => ({ value: tool.name, label: tool.name }))}
                  value={toolName}
                  onChange={(name) => selectTool(name, tools)}
                />
              </FormField>
              <FormField
                htmlFor="script-test-args"
                label="Arguments"
                error={argsError ?? undefined}
              >
                <Textarea
                  id="script-test-args"
                  rows={4}
                  className="font-mono text-xs"
                  value={argsText}
                  onChange={(event) => setArgsText(event.target.value)}
                />
              </FormField>
              <div className="flex justify-end">
                <Button
                  variant="secondary"
                  onClick={handleRun}
                  disabled={runAction.inFlight || !toolName}
                  status={runAction.status}
                  pendingLabel="Running…"
                >
                  Run
                </Button>
              </div>
            </>
          ))}

        {result && (
          <FormField htmlFor="script-test-output" label="Output">
            <JsonBlock
              value={result.structured ?? (result.content ?? []).join("\n")}
              tone={result.isError ? "error" : "default"}
            />
          </FormField>
        )}
      </div>
    </FormField>
  );
}
