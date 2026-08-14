/** @module useUserNames — resolves user ids to display names for table cells. */
"use client";

import { useEffect, useState } from "react";
import { getUserNames } from "@/lib/api";

/**
 * Resolve a set of user ids to display names, re-resolving whenever the set of
 * ids changes.
 *
 * Best-effort: a failed lookup leaves `names` at whatever it last held, so
 * callers falling back to the raw id (as {@link auditColumns} does) degrade
 * gracefully instead of showing nothing.
 *
 * @param ids - User ids to resolve, e.g. `rows.flatMap((r) => [r.createdBy, r.updatedBy])`.
 *   May contain duplicates or falsy values (`getUserNames` dedupes and drops them).
 * @returns Map from user id to display name, empty until the first resolution lands.
 */
export function useUserNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  // A comma-joined key of the filtered ids lets the effect depend on the set
  // of ids actually being resolved, not the identity of whatever array/iterable
  // the caller happened to construct this render.
  const idsKey = [...ids].filter((id): id is string => !!id).join(",");

  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    getUserNames(idsKey.split(","))
      .then((resolved) => {
        if (active) setNames(resolved);
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
