/**
 * @module UserPicker — Multi-select over the tenant's users, used to edit a group's members.
 *
 * Platform-scoped accounts (`tenantId === null` — every super admin and the
 * seeded system user) are filtered out: the backend refuses them as members,
 * since a group belongs to exactly one tenant. Soft-deleted users never reach
 * the list endpoint at all.
 */
"use client";

import { Users } from "lucide-react";
import { useCallback } from "react";
import { AsyncCheckboxPicker, type PickerOption } from "@/components/admin/async-checkbox-picker";
import { formatUserName, listUsers } from "@/lib/api";

/** Upper bound on the users offered, matching the API's page-size ceiling. */
const MAX_USERS = 1000;

/** Props for {@link UserPicker}. */
export interface UserPickerProps {
  /** Ids of the currently selected users. */
  value: string[];
  /** Called with the next selection whenever a user is toggled. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of a checkbox group. */
  readOnly?: boolean;
}

/** Controlled multi-select over the tenant's users. */
export function UserPicker({ value, onChange, readOnly = false }: UserPickerProps) {
  const load = useCallback(async (): Promise<PickerOption[]> => {
    const users = await listUsers({ limit: MAX_USERS });
    return users
      .filter((user) => user.tenantId !== null && user.tenantId !== undefined)
      .map((user) => ({
        value: user.id,
        label: `${formatUserName(user)} (${user.username})`,
      }));
  }, []);

  return (
    <AsyncCheckboxPicker
      label="Members"
      icon={Users}
      name="memberIds"
      value={value}
      onChange={onChange}
      load={load}
      readOnly={readOnly}
      loadingMessage="Fetching the users in this tenant."
      errorMessage="Could not load the users in this tenant."
      emptyMessage="This tenant has no users to add."
      filterLabel="Filter users"
    />
  );
}
