/**
 * @module UserGroupColumns — `UserGroup` table columns shared by the
 * user-groups list page and {@link GroupPicker}'s dialog table.
 *
 * The two surfaces render the same `UserGroup` row everywhere except the
 * identifier column: the list page's **Name** links to the group's detail
 * page, the picker's does not (picking a group is not a navigation), so that
 * one column stays local to each caller. Everything else — Description,
 * Roles, Members — is identical, and living here once is what keeps the two
 * from drifting the way {@link UserColumns} caught the users list page and
 * {@link UserPicker} having already done.
 */
import type { ColumnDef } from "@/components/ui/data-table";
import type { UserGroup } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { ROLE_LABELS } from "@/lib/roles";

/**
 * Description, Roles, and Members columns of a `UserGroup` row — byte-for-byte
 * the same table cells whether rendered by the user-groups list page or by
 * {@link GroupPicker}'s picker dialog.
 */
export const USER_GROUP_SHARED_COLUMNS: ColumnDef<UserGroup>[] = [
  {
    header: "Description",
    filterField: "description",
    cell: (g) => g.description || EMPTY_VALUE,
  },
  {
    // Roles are a JSON column, so this column is display-only: the list API can
    // neither sort nor filter on it.
    header: "Roles",
    noTruncate: true,
    cell: (g) =>
      g.roles && g.roles.length > 0
        ? g.roles.map((role) => ROLE_LABELS[role]).join(", ")
        : EMPTY_VALUE,
  },
  {
    // Membership lives in a join table rather than on the group row, so this is
    // display-only too.
    header: "Members",
    className: "text-center",
    cell: (g) => g.memberIds?.length ?? 0,
  },
];
