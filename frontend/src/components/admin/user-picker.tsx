/**
 * @module UserPicker — Assigns the tenant's users to one group.
 *
 * The listing is filtered server-side to the acting tenant. That is both what
 * keeps paging honest — a client-side filter would punch holes in pages — and
 * what keeps the picker from offering members the backend will reject: a group
 * belongs to exactly one tenant, so platform-scoped accounts (every super admin
 * and the seeded system user, all with `tenantId === null`) and users of other
 * tenants can never be members. Soft-deleted users never reach the list
 * endpoint at all.
 */
"use client";

import { User as UserIcon } from "lucide-react";
import { useCallback } from "react";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { RecordPickerField } from "@/components/admin/record-picker-field";
import { USER_SHARED_COLUMNS } from "@/components/admin/user-columns";
import type { ColumnDef } from "@/components/ui/data-table";
import { formatUserName, type ListQuery, listUsers, type User } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

/**
 * Columns of the picker dialog. Username is local — the dialog does not link
 * off to the user's detail page — the rest is shared with the users list
 * page via {@link USER_SHARED_COLUMNS}.
 */
const COLUMNS: ColumnDef<User>[] = [
  {
    header: "Username",
    sortField: "username",
    filterField: "username",
    visibility: "always",
    cell: (u) => u.username,
  },
  ...USER_SHARED_COLUMNS,
];

/** Label shown on a member's chip and on its checkbox in the dialog. */
function memberLabel(user: User): string {
  return `${formatUserName(user)} (${user.username})`;
}

/**
 * Props for {@link UserPicker}.
 *
 * Unlike {@link GroupPickerProps}, there is no `initialOptions`: a
 * `UserGroup` record carries `memberIds`, but nothing else on this page
 * already holds user labels for the page to hand over, so there is nothing
 * to seed the chips with.
 */
export interface UserPickerProps {
  /** Ids of the currently selected users. */
  value: string[];
  /** Called with the next selection whenever the assignment changes. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of an editable field. */
  readOnly?: boolean;
}

/** Controlled multi-select over the acting tenant's users. */
export function UserPicker({ value, onChange, readOnly = false }: UserPickerProps) {
  // The acting tenant, resolved the same way the X-Tenant-Id interceptor does:
  // a tenant-scoped viewer's own tenant, or the tenant a super admin selected
  // in the app bar.
  const viewerTenantId = useAppSelector((s) => s.auth.user?.tenantId ?? null);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantId = viewerTenantId ?? selectedTenantId;

  const listRecords = useCallback(
    (query: ListQuery) =>
      listUsers({
        ...query,
        filters: [
          ...(query.filters ?? []),
          // `tenantId` is only null here for a platform-scoped viewer with no
          // tenant selected, and that combination cannot actually reach this
          // component: `CurrentTenantIdDep` (backend) raises `ForbiddenError`
          // for such a caller, so the page's own tenant-scoped load already
          // fails with a 403 before any picker renders. The guard below is
          // still worth keeping explicit rather than assuming it can never
          // fire, since it's cheap and the invariant lives outside this file.
          ...(tenantId ? [{ field: "tenantId", op: "eq", value: tenantId }] : []),
        ],
      }),
    [tenantId]
  );

  const resolveLabels = useCallback(async (ids: string[]): Promise<PickerOption[]> => {
    const users = await listUsers({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return users.map((user) => ({ value: user.id, label: memberLabel(user) }));
  }, []);

  return (
    <RecordPickerField<User>
      label="Members"
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      resolveLabels={resolveLabels}
      listRecords={listRecords}
      columns={COLUMNS}
      getId={(user) => user.id}
      getLabel={memberLabel}
      panelId="user-picker-dialog"
      dialogTitle="Select members"
      selectLabel="Select members…"
      emptyMessage="This tenant has no users to add."
      emptyIcon={UserIcon}
    />
  );
}
