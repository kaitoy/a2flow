/** @module useTags — loads the tenant's full tag vocabulary for pickers and chip rendering. */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listTags, type Tag } from "@/lib/api";

/**
 * Page size for the tag fetch: the API's maximum.
 *
 * Tags are a curated vocabulary, not a growing record set, so the whole list is
 * loaded at once rather than paged — every consumer needs all of them to render
 * a picker or resolve an id to a name.
 */
const TAG_FETCH_LIMIT = 1000;

/** Everything a consumer needs to render tags by id. */
export interface UseTagsResult {
  /** Every tag in the tenant, in the API's order (by name). */
  tags: Tag[];
  /** The same tags keyed by id, for resolving a record's `tagIds`. */
  byId: Map<string, Tag>;
  /** True until the first fetch settles. */
  loading: boolean;
  /** Re-run the fetch, e.g. after a tag was created or renamed. */
  reload: () => Promise<void>;
}

/**
 * Load the tenant's tags.
 *
 * Fetched per mount rather than through a module-level cache: a cache shared
 * across pages would keep showing a stale name after a rename or a deleted tag
 * after a delete, and the list is small enough that one request per screen is
 * not worth that class of bug. A failed fetch surfaces as the global red toast
 * (see `api.ts`) and leaves the list empty.
 *
 * @returns The tags, an id lookup, the loading flag, and a manual reload.
 */
export function useTags(): UseTagsResult {
  const [tags, setTags] = useState<Tag[]>([]);
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
      const next = await listTags({ limit: TAG_FETCH_LIMIT });
      if (mountedRef.current) setTags(next);
    } catch {
      // Failure toast is shown globally by api.ts; the list stays as it was.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { tags, byId: new Map(tags.map((tag) => [tag.id, tag])), loading, reload };
}
