/**
 * @module tag-columns — the shared Tags column for every taggable admin list.
 *
 * One definition rather than six copies, following
 * {@link userGroupSharedColumns}: every taggable list renders tags identically
 * and filters them through the same axis, so the column that does it belongs in
 * one place.
 */
"use client";

import type { CheckboxOption } from "@/components/ui/checkbox-group";
import { ChipRow, type ChipRowItem } from "@/components/ui/chip-row";
import type { ColumnDef } from "@/components/ui/data-table";
import type { Tag } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { resolveTagColor } from "@/lib/tag-palette";

/**
 * Build the Tags column for a list of records carrying `tagIds`.
 *
 * The column is filterable but not sortable: a record holds a *set* of tags,
 * and there is no meaningful order over sets. Filtering runs on its own axis
 * (`filterKind: "tags"`, read and written through the table's `tagIds` /
 * `onTagIdsChange` props) because tags are not a column of any record and the
 * list API takes them as their own repeatable parameter.
 *
 * A tag id with no matching tag renders as the raw id rather than vanishing, so
 * a row never silently loses a chip when the tag list is momentarily stale.
 *
 * The chips are laid out by {@link ChipRow}, which holds the cell to one line
 * and folds the tags that do not fit into a `+N` chip that opens a dialog
 * listing every tag on the row, each with its description — so a heavily tagged
 * record neither grows its row nor claims the column's whole width.
 *
 * @param getTagIds - Reads the tag ids off a row.
 * @param byId - The tenant's tags keyed by id, from `useTags`.
 * @returns The column definition, ready to drop into a list's `columns` array.
 */
export function tagsColumn<T>(
  getTagIds: (row: T) => string[] | undefined,
  byId: Map<string, Tag>
): ColumnDef<T> {
  return {
    header: "Tags",
    // A row of chips is not text, so the default single-line truncation would
    // clip it mid-pill; `ChipRow` does its own clipping instead, folding what
    // does not fit into a `+N` chip.
    noTruncate: true,
    // That fold is this cell's ellipsis, so the column can give ground to the
    // panel fit like a text column rather than holding its full natural width.
    shrinkable: true,
    filterKind: "tags",
    tagOptions: tagFilterOptions(byId),
    cell: (row) => {
      const ids = getTagIds(row) ?? [];
      if (ids.length === 0) return EMPTY_VALUE;
      const items: ChipRowItem[] = ids.map((id) => ({
        key: id,
        label: byId.get(id)?.name ?? id,
        color: resolveTagColor(byId.get(id)?.color),
        description: byId.get(id)?.description ?? undefined,
      }));
      return <ChipRow items={items} title="Tags" />;
    },
  };
}

/**
 * Turn the tag lookup into the options the column's filter menu offers.
 *
 * @param byId - The tenant's tags keyed by id, from `useTags`.
 * @returns One checkbox option per tag, carrying its palette swatch.
 */
export function tagFilterOptions(byId: Map<string, Tag>): CheckboxOption[] {
  return [...byId.values()].map((tag) => ({
    value: tag.id,
    label: tag.name,
    swatch: resolveTagColor(tag.color),
  }));
}
