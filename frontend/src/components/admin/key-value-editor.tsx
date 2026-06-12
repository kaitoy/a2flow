/** @module KeyValueEditor — Controlled editor for a list of string key/value pairs. */
"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** One editable key/value row. */
export interface KeyValuePair {
  key: string;
  value: string;
}

/** Convert editor rows to a string map, dropping rows with an empty key. */
export function pairsToRecord(pairs: KeyValuePair[]): Record<string, string> {
  return Object.fromEntries(
    pairs.filter((p) => p.key.trim() !== "").map((p) => [p.key.trim(), p.value])
  );
}

/** Convert a string map to editor rows, in the map's iteration order. */
export function recordToPairs(record: Record<string, string>): KeyValuePair[] {
  return Object.entries(record).map(([key, value]) => ({ key, value }));
}

/** Props for {@link KeyValueEditor}. */
export interface KeyValueEditorProps {
  /** Field name used to derive stable input ids and aria labels. */
  name: string;
  /** Current rows, in display order. */
  pairs: KeyValuePair[];
  /** Called with the full replacement row list on every edit. */
  onChange: (pairs: KeyValuePair[]) => void;
  /** Placeholder for the key inputs. */
  keyPlaceholder?: string;
  /** Placeholder for the value inputs. */
  valuePlaceholder?: string;
}

/**
 * Editable list of key/value rows with add/remove controls, used for free-form
 * string maps such as the HTTP headers of a registered MCP server. Rows are
 * controlled by the caller (e.g. a react-hook-form Controller): every keystroke
 * reports the full replacement list via {@link KeyValueEditorProps.onChange}.
 */
export function KeyValueEditor({
  name,
  pairs,
  onChange,
  keyPlaceholder = "Key",
  valuePlaceholder = "Value",
}: KeyValueEditorProps) {
  function updateRow(index: number, patch: Partial<KeyValuePair>) {
    onChange(pairs.map((pair, i) => (i === index ? { ...pair, ...patch } : pair)));
  }

  function removeRow(index: number) {
    onChange(pairs.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-2">
      {pairs.map((pair, index) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: rows have no stable identity while being edited
          key={index}
          className="flex items-center gap-2"
        >
          <Input
            aria-label={`${name} key ${index + 1}`}
            placeholder={keyPlaceholder}
            value={pair.key}
            onChange={(e) => updateRow(index, { key: e.target.value })}
          />
          <Input
            aria-label={`${name} value ${index + 1}`}
            placeholder={valuePlaceholder}
            value={pair.value}
            onChange={(e) => updateRow(index, { value: e.target.value })}
          />
          <Button
            type="button"
            variant="ghost"
            aria-label={`Remove ${name} row ${index + 1}`}
            onClick={() => removeRow(index)}
            className="text-error"
          >
            ✕
          </Button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => onChange([...pairs, { key: "", value: "" }])}
        >
          + Add row
        </Button>
      </div>
    </div>
  );
}
