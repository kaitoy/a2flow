/**
 * @module GroupPicker — Multi-select over the tenant's user groups, used to edit one user's membership.
 *
 * The counterpart of {@link UserPicker}: membership is editable from either
 * side, so an admin can manage it from whichever page they are already on.
 */
"use client";

import { UsersRound } from "lucide-react";
import { useCallback } from "react";
import { AsyncCheckboxPicker, type PickerOption } from "@/components/admin/async-checkbox-picker";
import { listUserGroups } from "@/lib/api";

/** Upper bound on the groups offered, matching the API's page-size ceiling. */
const MAX_GROUPS = 1000;

/** Props for {@link GroupPicker}. */
export interface GroupPickerProps {
  /** Ids of the groups the user currently belongs to. */
  value: string[];
  /** Called with the next selection whenever a group is toggled. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of a checkbox group. */
  readOnly?: boolean;
}

/** Controlled multi-select over the tenant's user groups. */
export function GroupPicker({ value, onChange, readOnly = false }: GroupPickerProps) {
  const load = useCallback(async (): Promise<PickerOption[]> => {
    const groups = await listUserGroups({ limit: MAX_GROUPS });
    return groups.map((group) => ({ value: group.id, label: group.name }));
  }, []);

  return (
    <AsyncCheckboxPicker
      label="Groups"
      icon={UsersRound}
      name="groupIds"
      value={value}
      onChange={onChange}
      load={load}
      readOnly={readOnly}
      loadingMessage="Fetching the user groups in this tenant."
      errorMessage="Could not load the user groups in this tenant."
      emptyMessage="This tenant has no user groups yet."
      filterLabel="Filter groups"
    />
  );
}
