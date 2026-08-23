/**
 * @module tag-columns — the shared Tags column for every taggable admin list.
 *
 * One definition rather than four copies, following
 * {@link USER_GROUP_SHARED_COLUMNS}: the four taggable lists render tags
 * identically and filter them through the same axis, so the column that does it
 * belongs in one place.
 */
"use client";

import type { CheckboxOption } from "@/components/ui/checkbox-group";
import { Chip } from "@/components/ui/chip";
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
    // Chips wrap onto as many lines as the row needs, so the default
    // single-line truncation would clip them; each Chip clips its own label.
    noTruncate: true,
    filterKind: "tags",
    tagOptions: tagFilterOptions(byId),
    cell: (row) => {
      const ids = getTagIds(row) ?? [];
      if (ids.length === 0) return EMPTY_VALUE;
      return (
        <div className="flex flex-wrap gap-1">
          {ids.map((id) => (
            <Chip
              key={id}
              label={byId.get(id)?.name ?? id}
              color={resolveTagColor(byId.get(id)?.color)}
              description={byId.get(id)?.description ?? undefined}
            />
          ))}
        </div>
      );
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
