/** @module StringListEditor — Controlled editor for an ordered list of strings. */
"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Props for {@link StringListEditor}. */
export interface StringListEditorProps {
  /** Field name used to derive stable aria labels. */
  name: string;
  /** Current entries, in display order. */
  values: string[];
  /** Called with the full replacement list on every edit. */
  onChange: (values: string[]) => void;
  /** Placeholder for the entry inputs. */
  placeholder?: string;
  /** Label of the add-row button. */
  addLabel?: string;
}

/**
 * Editable list of single-string rows with add/remove controls, used where
 * order matters and there is no key — the `argv` entries of a stdio MCP server.
 * The list-of-pairs counterpart is `KeyValueEditor`. Rows are controlled by the
 * caller (e.g. a react-hook-form Controller): every keystroke reports the full
 * replacement list via {@link StringListEditorProps.onChange}.
 */
export function StringListEditor({
  name,
  values,
  onChange,
  placeholder = "Value",
  addLabel = "+ Add row",
}: StringListEditorProps) {
  function updateRow(index: number, value: string) {
    onChange(values.map((current, i) => (i === index ? value : current)));
  }

  function removeRow(index: number) {
    onChange(values.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-2">
      {values.map((value, index) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: rows have no stable identity while being edited
          key={index}
          className="flex items-center gap-2"
        >
          <Input
            aria-label={`${name} value ${index + 1}`}
            placeholder={placeholder}
            value={value}
            onChange={(e) => updateRow(index, e.target.value)}
          />
          <Button
            type="button"
            variant="danger"
            aria-label={`Remove ${name} row ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ✕
          </Button>
        </div>
      ))}
      <div>
        <Button type="button" variant="secondary" onClick={() => onChange([...values, ""])}>
          {addLabel}
        </Button>
      </div>
    </div>
  );
}
