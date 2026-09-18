/**
 * @module group-columns — the shared Groups column for a record carrying
 * `groupIds`.
 *
 * Mirrors {@link tagsColumn}: the chip layout, two-line fold, overflow dialog,
 * and hover-description tooltip all live in {@link ChipRow}, so this column
 * only maps ids to chip data. `UserGroup` has no `color` field the way `Tag`
 * does, so every chip renders as the neutral glass chip. The filter menu
 * mirrors it too, through `filterKind: "groups"` — the analogous axis
 * `DataTable` offers alongside `"tags"`, backed by the `group` query
 * parameter `GET /users` accepts.
 */
"use client";

import type { CheckboxOption } from "@/components/ui/checkbox-group";
import { ChipRow, type ChipRowItem } from "@/components/ui/chip-row";
import type { ColumnDef } from "@/components/ui/data-table";
import type { UserGroup } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/**
 * Build the Groups column for a list of records carrying `groupIds`.
 *
 * A group id with no matching group renders as the raw id rather than
 * vanishing, so a row never silently loses a chip when the group list is
 * momentarily stale.
 *
 * @param getGroupIds - Reads the group ids off a row.
 * @param byId - The tenant's groups keyed by id, from `useGroups`.
 * @returns The column definition, ready to drop into a list's `columns` array.
 */
export function groupsColumn<T>(
  getGroupIds: (row: T) => string[] | undefined,
  byId: Map<string, UserGroup>
): ColumnDef<T> {
  return {
    header: "Groups",
    // A row of chips is not text, so the default single-line truncation would
    // clip it mid-pill; `ChipRow` does its own clipping instead, wrapping to at
    // most two lines and folding the rest into a `+N` chip.
    noTruncate: true,
    // That fold is this cell's ellipsis, so the column can give ground to the
    // panel fit like a text column rather than holding its full natural width.
    shrinkable: true,
    // Trim the body cell's vertical padding (`!` to beat the `<td>`'s own
    // `py-3`) so two `xs` chip lines occupy the height one `sm` line did, and
    // keep it vertically centred (the table's default, restated here so it
    // survives the padding override) so a one-line row sits mid-cell.
    className: "py-1! align-middle",
    filterKind: "groups",
    groupOptions: groupFilterOptions(byId),
    cell: (row) => {
      const ids = getGroupIds(row) ?? [];
      if (ids.length === 0) return EMPTY_VALUE;
      const items: ChipRowItem[] = ids.map((id) => ({
        key: id,
        label: byId.get(id)?.name ?? id,
        description: byId.get(id)?.description ?? undefined,
      }));
      return <ChipRow items={items} title="Groups" />;
    },
  };
}

/**
 * Turn the group lookup into the options the column's filter menu offers.
 *
 * @param byId - The tenant's groups keyed by id, from `useGroups`.
 * @returns One checkbox option per group.
 */
export function groupFilterOptions(byId: Map<string, UserGroup>): CheckboxOption[] {
  return [...byId.values()].map((group) => ({ value: group.id, label: group.name }));
}
