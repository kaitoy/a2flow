/**
 * @module TagPicker — shared tag multi-select for the taggable admin forms.
 *
 * Used by the secret, MCP server, agent skill, and workflow forms so the four
 * stay in step, the same way {@link McpToolPicker} is shared across the task
 * template forms.
 *
 * Deliberately not built on {@link RecordPickerField} / {@link RecordPickerDialog}:
 * those exist for record sets too large to render at once and carry a modal
 * with server-side paging. Tags are a small curated vocabulary, so this follows
 * {@link McpToolPicker} instead — load them all, render a checkbox group, and
 * add a filter box only once the list gets long.
 */
"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useTags } from "@/hooks/useTags";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { resolveTagColor } from "@/lib/tag-palette";

/** Option count above which a filter box is worth showing. */
const FILTER_THRESHOLD = 12;

/** Props for {@link TagPicker}. */
export interface TagPickerProps {
  /** Ids of the currently selected tags. */
  value: string[];
  /** Called with the next selection whenever a tag is toggled or removed. */
  onChange: (next: string[]) => void;
  /**
   * Renders the attached tags as a value instead of a picker, for a viewer
   * whose role cannot write this record. `onChange` is then never called.
   */
  readOnly?: boolean;
  /** Label above the picker. */
  label?: string;
}

/**
 * Controlled multi-select over the tenant's tags.
 *
 * The current selection is shown above the group as colored chips carrying a
 * remove button, so a long vocabulary never hides what is already attached.
 * Selected tags are also kept in the filtered list — {@link CheckboxGroup}
 * derives the next selection from the options it was handed, so filtering one
 * out would silently drop it.
 *
 * An id with no matching tag is rendered as a chip labelled with the id itself
 * rather than dropped: that only happens when a tag was deleted between the
 * record being loaded and this list being fetched, and quietly discarding it
 * would save the record with a tag the user never chose to remove.
 */
export function TagPicker({ value, onChange, readOnly = false, label = "Tags" }: TagPickerProps) {
  const { tags, byId, loading } = useTags();
  const [query, setQuery] = useState("");

  const selected = useMemo(
    () =>
      value.map((id) => ({
        id,
        name: byId.get(id)?.name ?? id,
        color: resolveTagColor(byId.get(id)?.color),
      })),
    [value, byId]
  );

  const options: CheckboxOption[] = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return tags
      .filter((tag) => !needle || tag.name.toLowerCase().includes(needle) || value.includes(tag.id))
      .map((tag) => ({ value: tag.id, label: tag.name, swatch: resolveTagColor(tag.color) }));
  }, [tags, query, value]);

  if (readOnly) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-label-caps">{label}</span>
        {selected.length === 0 ? (
          <ReadOnlyField>{EMPTY_VALUE}</ReadOnlyField>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {selected.map((tag) => (
              <Chip key={tag.id} label={tag.name} color={tag.color} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">{label}</span>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((tag) => (
            <Chip
              key={tag.id}
              label={tag.name}
              color={tag.color}
              onRemove={() => onChange(value.filter((id) => id !== tag.id))}
            />
          ))}
        </div>
      )}
      {loading ? (
        <Skeleton className="h-24 rounded-xl" />
      ) : tags.length === 0 ? (
        <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
          No tags are registered yet.{" "}
          <Link href="/admin/tags" className="text-accent transition-colors hover:underline">
            Create one
          </Link>{" "}
          to start classifying records.
        </p>
      ) : (
        <>
          {tags.length > FILTER_THRESHOLD && (
            <Input
              aria-label="Filter tags"
              placeholder="Filter tags…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          <CheckboxGroup
            name="tagIds"
            options={options}
            value={value}
            onChange={onChange}
            emptyMessage="No tags match the filter."
          />
        </>
      )}
    </div>
  );
}
