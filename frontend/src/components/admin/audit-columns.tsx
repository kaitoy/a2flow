/**
 * @module audit-columns — the shared audit columns (ID, Updated At, Created By,
 * Updated By) for every admin list.
 *
 * One definition rather than a dozen copies, following {@link tagsColumn}: every
 * `WithAudit` record carries the same four fields, so the columns that display
 * them belong in one place.
 */
"use client";

import Link from "next/link";
import type { ColumnDef } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";

/** The audit fields every `WithAudit<T>` row carries. */
interface Audited {
  id: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
}

/**
 * Build the ID / Updated At / Created By / Updated By columns shared by every
 * admin list. All four are `visibility: "optional"` — they're implementation
 * detail rather than a record's primary content, so they stay out of the way
 * until a viewer asks for them via the column picker.
 *
 * ID deliberately carries no `sortField`/`filterField` even though the cell
 * shows the literal underlying value and so could technically be sorted or
 * filtered: keeping it display-only means a column's interactive behavior
 * doesn't silently change depending on whether the calling page happens to
 * have a name lookup in scope. Created By and Updated By link to the user's
 * detail page regardless of whether `userNameById` was supplied — with no map,
 * the link is simply labeled with the raw id, mirroring the Initiator column's
 * fallback.
 *
 * @param userNameById - Optional map from user id to display name, built by
 *   whatever lookup the calling page already runs for its own columns (e.g. an
 *   Approver or Initiator column). This builder never fetches names itself; a
 *   page with no such lookup simply gets raw ids, the same fallback
 *   {@link AuditMeta} uses.
 * @returns The four column definitions, ready to append to a list's `columns` array.
 */
export function auditColumns<T extends Audited>(
  userNameById?: Map<string, string>
): ColumnDef<T>[] {
  const nameOf = (id: string) => userNameById?.get(id) ?? id;
  const userLink = (id: string) => (
    <Link
      href={`/admin/users/${id}`}
      className="font-medium text-accent transition-colors hover:underline"
    >
      {nameOf(id)}
    </Link>
  );
  return [
    {
      header: "ID",
      visibility: "optional",
      className: "font-mono",
      cell: (row) => row.id,
    },
    {
      header: "Updated At",
      visibility: "optional",
      sortField: "updatedAt",
      cell: (row) => <DateTime value={row.updatedAt} className="text-on-surface-variant" />,
    },
    {
      header: "Created By",
      visibility: "optional",
      cell: (row) => userLink(row.createdBy),
    },
    {
      header: "Updated By",
      visibility: "optional",
      cell: (row) => userLink(row.updatedBy),
    },
  ];
}
