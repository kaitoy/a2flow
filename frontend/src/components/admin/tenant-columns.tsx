/**
 * @module tenant-columns — the shared Tenant column for admin lists browsable
 * across every tenant at once.
 */
"use client";

import Link from "next/link";
import type { ColumnDef } from "@/components/ui/data-table";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** A record carrying the tenant it belongs to. */
interface TenantScoped {
  tenantId?: string | null;
}

/**
 * Build the Tenant column shown when a Super Admin is browsing "All tenants"
 * (see {@link useIsAllTenantsView}) — otherwise every row on a list would
 * share the same tenant, making the column redundant. Links to the tenant's
 * detail page; falls back to the raw id if `tenantNameById` has no entry yet,
 * and to {@link EMPTY_VALUE} for a platform-scoped record with no tenant at
 * all (e.g. a Super Admin user).
 *
 * @param tenantNameById - Map from tenant id to display name, from {@link useTenantNames}.
 * @returns The column definition. Place it first in a list's `columns` array —
 *   ahead of {@link idColumn} — so which tenant a row belongs to is the
 *   leftmost thing the Super Admin reads.
 */
export function tenantColumn<T extends TenantScoped>(
  tenantNameById: Map<string, string>
): ColumnDef<T> {
  return {
    header: "Tenant",
    visibility: "default",
    cell: (row) => {
      const id = row.tenantId;
      if (!id) return EMPTY_VALUE;
      return (
        <Link
          href={`/admin/tenants/${id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {tenantNameById.get(id) ?? id}
        </Link>
      );
    },
  };
}
