/**
 * @module TagPicker — shared tag multi-select for the taggable admin forms.
 *
 * Used by the secret, MCP server, agent skill, and workflow forms so the four
 * stay in step, the same way {@link McpToolPicker} is shared across the task
 * template forms.
 *
 * Shaped like {@link RecordPickerField}: the attached tags read as a row of
 * removable chips and changing them opens a modal, so the field's height is the
 * selection's, not the vocabulary's. It does not *use* that component, though —
 * `RecordPickerField` pairs with a paged, server-filtered table and has to
 * resolve ids to labels over the network, while {@link useTags} already holds
 * the whole vocabulary and every chip here needs a color. The modal is
 * {@link TagPickerDialog} instead.
 */
"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { TagPickerDialog } from "@/components/admin/tag-picker-dialog";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { useTags } from "@/hooks/useTags";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { resolveTagColor } from "@/lib/tag-palette";

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
 * The current selection is shown as colored chips carrying a remove button, so
 * the common edit — dropping one tag — costs no dialog at all.
 *
 * An id with no matching tag is rendered as a chip labelled with the id itself
 * rather than dropped: that only happens when a tag was deleted between the
 * record being loaded and this list being fetched, and quietly discarding it
 * would save the record with a tag the user never chose to remove.
 */
export function TagPicker({ value, onChange, readOnly = false, label = "Tags" }: TagPickerProps) {
  const { tags, byId, loading } = useTags();
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);

  const selected = useMemo(
    () =>
      value.map((id) => ({
        id,
        name: byId.get(id)?.name ?? id,
        color: resolveTagColor(byId.get(id)?.color),
        description: byId.get(id)?.description ?? undefined,
      })),
    [value, byId]
  );

  const chips =
    selected.length === 0 ? (
      <ReadOnlyField>{EMPTY_VALUE}</ReadOnlyField>
    ) : (
      <div className="flex flex-wrap gap-1.5">
        {selected.map((tag) => (
          <Chip
            key={tag.id}
            label={tag.name}
            color={tag.color}
            description={tag.description}
            onRemove={readOnly ? undefined : () => onChange(value.filter((id) => id !== tag.id))}
          />
        ))}
      </div>
    );

  if (readOnly) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-label-caps">{label}</span>
        {chips}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">{label}</span>
      {chips}
      {loading ? (
        <Skeleton className="h-9 w-40 rounded-xl" />
      ) : tags.length === 0 ? (
        // Shown in place of the button rather than inside the dialog: there is
        // nothing to pick, so opening one would be a dead end.
        <p className="rounded-xl glass-panel px-4 py-3 text-sm text-on-surface-variant">
          No tags are registered yet.{" "}
          <Link href="/admin/tags" className="text-accent transition-colors hover:underline">
            Create one
          </Link>{" "}
          to start classifying records.
        </p>
      ) : (
        <div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setEverOpened(true);
              setOpen(true);
            }}
          >
            Select tags…
          </Button>
        </div>
      )}
      {/* Mounted on the first open and then kept mounted, so it costs nothing
          until asked for and its leave animation still has a component to run
          on — the same lifecycle RecordPickerField gives its dialog. */}
      {everOpened && (
        <TagPickerDialog
          open={open}
          onClose={() => setOpen(false)}
          onAssign={(ids) => {
            onChange(ids);
            setOpen(false);
          }}
          panelId="tag-picker-dialog"
          value={value}
          tags={tags}
        />
      )}
    </div>
  );
}
