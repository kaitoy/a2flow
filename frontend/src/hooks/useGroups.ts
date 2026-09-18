/** @module useGroups — loads the tenant's full user-group vocabulary for chip rendering. */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listUserGroups, type UserGroup } from "@/lib/api";

/**
 * Page size for the group fetch: the API's maximum.
 *
 * Groups are a curated vocabulary, not a growing record set, so the whole list is
 * loaded at once rather than paged — every consumer needs all of them to render
 * a picker or resolve an id to a name.
 */
const GROUP_FETCH_LIMIT = 1000;

/** Everything a consumer needs to render groups by id. */
export interface UseGroupsResult {
  /** Every group in the tenant, in the API's order (by name). */
  groups: UserGroup[];
  /** The same groups keyed by id, for resolving a record's `groupIds`. */
  byId: Map<string, UserGroup>;
  /** True until the first fetch settles. */
  loading: boolean;
  /** Re-run the fetch, e.g. after a group was created or renamed. */
  reload: () => Promise<void>;
}

/**
 * Load the tenant's user groups.
 *
 * Fetched per mount rather than through a module-level cache: a cache shared
 * across pages would keep showing a stale name after a rename or a deleted group
 * after a delete, and the list is small enough that one request per screen is
 * not worth that class of bug. A failed fetch surfaces as the global red toast
 * (see `api.ts`) and leaves the list empty.
 *
 * @returns The groups, an id lookup, the loading flag, and a manual reload.
 */
export function useGroups(): UseGroupsResult {
  const [groups, setGroups] = useState<UserGroup[]>([]);
  const [loading, setLoading] = useState(true);

  // Guards the post-await state update. Re-asserted on mount because React
  // StrictMode mounts, unmounts, then remounts in development.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    try {
      const next = await listUserGroups({ limit: GROUP_FETCH_LIMIT });
      if (mountedRef.current) setGroups(next);
    } catch {
      // Failure toast is shown globally by api.ts; the list stays as it was.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { groups, byId: new Map(groups.map((group) => [group.id, group])), loading, reload };
}
