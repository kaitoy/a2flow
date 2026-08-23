/**
 * @module TagPickerDialog — modal grid for choosing which tags a record carries.
 *
 * The tag counterpart of {@link RecordPickerDialog}, sharing its outer contract
 * (a draft selection, Cancel discards, Select confirms) but none of its body.
 * That dialog is built for a record set too large to render at once, so it pages
 * and filters a {@link DataTable} server-side; tags are the opposite — a small
 * curated vocabulary {@link useTags} already holds whole — so they are laid out
 * as a wrapping grid of toggle chips, narrowed client-side by name and by
 * palette slot.
 *
 * Deliberately takes its tags as a prop instead of calling `useTags` itself, so
 * the dialog stays a pure rendering of what the field already fetched.
 */
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Tag, TagColor } from "@/lib/api";
import { resolveTagColor, TAG_COLOR_CLASS, TAG_COLORS, tagColorLabel } from "@/lib/tag-palette";

/** Props for {@link TagPickerDialog}. */
export interface TagPickerDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog requests to close (Cancel, backdrop, or Escape). */
  onClose: () => void;
  /** Called with the confirmed selection on Select. */
  onAssign: (ids: string[]) => void;
  /** DOM id of the dialog panel; must be unique on the page. */
  panelId: string;
  /** Ids already attached; the draft is seeded from these on every open. */
  value: string[];
  /** The tenant's full tag vocabulary, from {@link useTags}. */
  tags: Tag[];
}

/** Props for {@link ColorFilter}. */
interface ColorFilterProps {
  /** Slots currently filtered on. Empty means no color narrowing at all. */
  value: TagColor[];
  /** Called with the next slot list whenever a swatch is toggled. */
  onChange: (next: TagColor[]) => void;
}

/**
 * Row of palette swatches narrowing the grid to the slots pressed.
 *
 * Multi-select rather than one-of-eight, and with no explicit "All" option:
 * pressing every swatch off *is* the cleared state, which keeps the control to
 * eight round targets instead of nine. Each swatch is a real toggle button
 * carrying `aria-pressed` and the slot's name, so the filter is operable
 * without seeing the colors at all.
 *
 * Local to this module: it exists to filter this grid, and a second call site
 * is the moment to lift it into `components/ui`.
 */
function ColorFilter({ value, onChange }: ColorFilterProps) {
  return (
    <div className="flex shrink-0 items-center gap-0.5">
      {TAG_COLORS.map((color) => {
        const pressed = value.includes(color);
        return (
          <button
            key={color}
            type="button"
            aria-pressed={pressed}
            aria-label={tagColorLabel(color)}
            onClick={() => onChange(pressed ? value.filter((c) => c !== color) : [...value, color])}
            className={[
              "inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-full",
              "pointer-coarse:size-9",
              "transition-colors duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
              pressed ? "bg-accent-soft" : "hover:bg-accent-soft/40",
            ].join(" ")}
          >
            <span
              aria-hidden="true"
              className={`size-3 rounded-full tag-swatch ${TAG_COLOR_CLASS[color]} ${
                pressed ? "" : "opacity-45"
              }`}
            />
          </button>
        );
      })}
    </div>
  );
}

/**
 * Modal grid that returns a set of tag ids.
 *
 * The draft selection lives in component state rather than being derived from
 * the rendered options, which is the whole reason this replaces the old inline
 * checkbox list: `CheckboxGroup` computes the next selection from the options it
 * was handed, so narrowing the list would silently drop any selected tag it
 * filtered out — the old picker had to keep selected tags pinned into the
 * filtered list to work around it. Here a tag stays selected while hidden, and
 * clearing the filter brings it back checked.
 *
 * Filters compose: a tag must match the name query *and* (when any swatch is
 * pressed) carry one of the pressed slots.
 */
export function TagPickerDialog({
  open,
  onClose,
  onAssign,
  panelId,
  value,
  tags,
}: TagPickerDialogProps) {
  const [draft, setDraft] = useState<string[]>(value);
  const [query, setQuery] = useState("");
  const [colors, setColors] = useState<TagColor[]>([]);
  const wasOpenRef = useRef(open);

  // Re-seed the draft and clear the filters on the closed→open transition, so a
  // cancelled edit never leaks into the next one and an assignment made
  // elsewhere is picked up. `value` is deliberately not a dependency: re-seeding
  // on every `value` identity change while already open would discard an
  // in-progress draft whenever the parent re-renders with a fresh (but equal)
  // array. Same reasoning as RecordPickerDialog's.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally re-runs only on the open transition, not on every value identity change
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setDraft(value);
      setQuery("");
      setColors([]);
    }
    wasOpenRef.current = open;
  }, [open]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return tags.filter(
      (tag) =>
        (!needle || tag.name.toLowerCase().includes(needle)) &&
        (colors.length === 0 || colors.includes(resolveTagColor(tag.color)))
    );
  }, [tags, query, colors]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId={panelId}
      title="Select tags"
      size="lg"
      scrollable
      footer={
        <>
          <span className="mr-auto text-sm text-on-surface-variant">{draft.length} selected</span>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" variant="primary" onClick={() => onAssign(draft)}>
            Select
          </Button>
        </>
      }
    >
      {/* Stacked below `sm`, where the eight swatches and the input cannot share
          a row without squeezing the input to a few characters. */}
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          aria-label="Filter tags"
          placeholder="Filter tags…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <ColorFilter value={colors} onChange={setColors} />
      </div>
      <div className="flex-1 overflow-y-auto">
        {visible.length === 0 ? (
          // No glass panel: this sits inside the dialog's own
          // `glass-panel-overlay`, and a second surface would stack two
          // elevation tiers — the same reason `CheckboxGroup` offers `flush`.
          <p className="px-1 py-2 text-sm text-on-surface-variant">No tags match the filter.</p>
        ) : (
          // Wrapping flex rather than a fixed-column grid: tag names vary in
          // length, so equal columns would leave a ragged gap beside every
          // short one.
          <div className="flex flex-wrap gap-2">
            {visible.map((tag) => (
              <Chip
                key={tag.id}
                label={tag.name}
                color={resolveTagColor(tag.color)}
                description={tag.description ?? undefined}
                selected={draft.includes(tag.id)}
                onToggle={() =>
                  setDraft((prev) =>
                    prev.includes(tag.id) ? prev.filter((id) => id !== tag.id) : [...prev, tag.id]
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}
