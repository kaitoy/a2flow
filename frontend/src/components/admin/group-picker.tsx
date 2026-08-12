/**
 * @module GroupPicker — Assigns the tenant's user groups to one user.
 *
 * The counterpart of {@link UserPicker}: membership is editable from either
 * side, so an admin can manage it from whichever page they are already on.
 */
"use client";

import { UsersRound } from "lucide-react";
import { useCallback } from "react";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { RecordPickerField } from "@/components/admin/record-picker-field";
import { USER_GROUP_SHARED_COLUMNS } from "@/components/admin/user-group-columns";
import type { ColumnDef } from "@/components/ui/data-table";
import { listUserGroups, type UserGroup } from "@/lib/api";

/**
 * Columns of the picker dialog. Name is local — the dialog does not link
 * off to the group's detail page — the rest is shared with the user-groups
 * list page via {@link USER_GROUP_SHARED_COLUMNS}.
 */
const COLUMNS: ColumnDef<UserGroup>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    visibility: "always",
    cell: (g) => g.name,
  },
  ...USER_GROUP_SHARED_COLUMNS,
];

/** Props for {@link GroupPicker}. */
export interface GroupPickerProps {
  /** Ids of the groups the user currently belongs to. */
  value: string[];
  /** Called with the next selection whenever the assignment changes. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of an editable field. */
  readOnly?: boolean;
  /** Group labels the page already loaded, saving a label round trip. */
  initialOptions?: PickerOption[];
}

/** Controlled multi-select over the tenant's user groups. */
export function GroupPicker({
  value,
  onChange,
  readOnly = false,
  initialOptions,
}: GroupPickerProps) {
  const resolveLabels = useCallback(async (ids: string[]): Promise<PickerOption[]> => {
    const groups = await listUserGroups({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return groups.map((group) => ({ value: group.id, label: group.name }));
  }, []);

  return (
    <RecordPickerField<UserGroup>
      label="Groups"
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      initialOptions={initialOptions}
      resolveLabels={resolveLabels}
      listRecords={listUserGroups}
      columns={COLUMNS}
      getId={(group) => group.id}
      getLabel={(group) => group.name}
      panelId="group-picker-dialog"
      dialogTitle="Select groups"
      selectLabel="Select groups…"
      emptyMessage="This tenant has no user groups yet."
      emptyIcon={UsersRound}
    />
  );
}
