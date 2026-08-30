/**
 * @module useTenantNames — resolves tenant ids to display names for table cells.
 *
 * Tenant `displayName` is a `super_admin`-only datum: the backend restricts
 * `GET /tenants` to that role by design (see `backend/routers/tenant.py`), and
 * the resolved names only ever surface in the cross-tenant "All tenants" view a
 * `super_admin` opens. Every other viewer gets a stable empty map and no
 * request. The sibling hooks {@link useWorkflowExecutionNames}, `useUserNames`,
 * and `useGroupNames` are deliberately left unguarded — their list endpoints are
 * open to any authenticated user.
 */
"use client";

import { useEffect, useState } from "react";
import { listTenants } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

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
 * Only a `super_admin` resolves anything: for any other role the lookup would be
 * rejected with HTTP 403, so the hook skips the request entirely and keeps
 * returning an empty map. Callers still render, falling back to the raw id.
 *
 * @param ids - Tenant ids to resolve, e.g. `rows.map((r) => r.tenantId)`. May
 *   contain duplicates or falsy values.
 * @returns Map from tenant id to its `displayName`, empty until the first
 *   resolution lands (and always empty for a non-`super_admin` viewer).
 */
export function useTenantNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());
  // GET /tenants is super_admin-only; asking as any other role only ever earns a
  // 403 (and a global error toast), so don't ask.
  const canResolveTenants = useHasRole(Role.SUPER_ADMIN);

  // Same keying trick as useWorkflowExecutionNames: depend on the set of ids
  // being resolved, not on the identity of the caller's array.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey || !canResolveTenants) return;
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
  }, [idsKey, canResolveTenants]);

  return names;
}
