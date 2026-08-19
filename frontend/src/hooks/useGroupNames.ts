/** @module useGroupNames — resolves user group ids to names for table cells. */
"use client";

import { useEffect, useState } from "react";
import { listUserGroups } from "@/lib/api";

/**
 * Resolve a set of user group ids to group names, re-resolving whenever the set
 * of ids changes.
 *
 * The counterpart of {@link useUserNames} for the other kind of id an approval
 * can be addressed to. It goes through the ordinary `GET /user-groups` list with
 * an `id:in:` filter rather than a dedicated resolve endpoint: `resolve-names`
 * exists for users because another user's name can be invisible to the caller,
 * and a group carries no such rule — it is a plain tenant-scoped record any
 * authenticated caller may already read in full.
 *
 * Best-effort in the same way: a failed lookup leaves `names` at whatever it
 * last held, so callers falling back to the raw id degrade gracefully.
 *
 * @param ids - Group ids to resolve. May contain duplicates or falsy values.
 * @returns Map from group id to group name, empty until the first resolution lands.
 */
export function useGroupNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  // Same keying trick as useUserNames: depend on the set of ids being
  // resolved, not on the identity of the caller's array.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    const wanted = idsKey.split(",");
    listUserGroups({
      limit: wanted.length,
      filters: [{ field: "id", op: "in", value: idsKey }],
    })
      .then((groups) => {
        if (active) setNames(new Map(groups.map((group) => [group.id, group.name])));
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
