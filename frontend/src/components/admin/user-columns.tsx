/**
 * @module UserColumns — `User` table columns shared by the users list page
 * and {@link UserPicker}'s dialog table.
 *
 * The two surfaces render the same `User` row everywhere except the
 * identifier column: the list page's **Username** links to the user's detail
 * page, the picker's does not (picking a user is not a navigation), so that
 * one column stays local to each caller. **Name** and **Email** are
 * identical and live here instead, so the two cannot silently drift apart —
 * which they already had: the picker built its Name cell from
 * {@link formatUserName} while the list page concatenated `firstName` and
 * `lastName` by hand.
 */
import type { ColumnDef } from "@/components/ui/data-table";
import { formatUserName, type User } from "@/lib/api";

/**
 * Name and Email columns of a `User` row — the same table cells whether
 * rendered by the users list page or by {@link UserPicker}'s picker dialog.
 *
 * `visibility: "optional"` on Email only matters to the list page — it opts
 * the column out of {@link useColumnVisibility}'s default-shown set there.
 * The picker dialog never calls that hook, so `DataTable` renders every
 * column it is given regardless of `visibility`, and the field is simply
 * inert for the picker.
 */
export const USER_SHARED_COLUMNS: ColumnDef<User>[] = [
  {
    header: "Name",
    sortField: "firstName",
    filterField: "firstName",
    cell: (u) => formatUserName(u),
  },
  {
    header: "Email",
    sortField: "email",
    filterField: "email",
    visibility: "optional",
    cell: (u) => u.email,
  },
];
