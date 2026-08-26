/** @module useTenantNames — resolves tenant ids to display names for table cells. */
"use client";

import { useEffect, useState } from "react";
import { listTenants } from "@/lib/api";

/**
 * Resolve a set of tenant ids to their `displayName`, re-resolving whenever the
 * set of ids changes.
 *
 * The counterpart of {@link useWorkflowExecutionNames} for tenants: no dedicated
 * resolve endpoint exists, so this goes through the ordinary `GET /tenants` with
 * an `id:in:` filter. Best-effort in the same way — a failed lookup leaves
 * `names` at whatever it last held, so callers falling back to the raw id
 * degrade gracefully.
 *
 * @param ids - Tenant ids to resolve, e.g. `rows.map((r) => r.tenantId)`. May
 *   contain duplicates or falsy values.
 * @returns Map from tenant id to its `displayName`, empty until the first resolution lands.
 */
export function useTenantNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  // Same keying trick as useWorkflowExecutionNames: depend on the set of ids
  // being resolved, not on the identity of the caller's array.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    const wanted = idsKey.split(",");
    listTenants({
      limit: wanted.length,
      filters: [{ field: "id", op: "in", value: idsKey }],
    })
      .then((tenants) => {
        if (active) setNames(new Map(tenants.map((t) => [t.id, t.displayName])));
      })
      .catch(() => {
        // Name resolution is best-effort; callers fall back to the raw id.
      });
    return () => {
      active = false;
    };
  }, [idsKey]);

  return names;
}
