/** @module useTableQuery — admin list state (pagination + server-side sort/filter). */
"use client";

import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type { FilterSpec, ListQuery, SortSpec } from "@/lib/api";

/** Options accepted by {@link UseTableQueryResult.reload}. */
export interface ReloadOptions {
  /**
   * Refetch without any loading indicator, keeping the current rows on screen.
   * Use for background polling, where a spinner on every tick reads as flicker.
   */
  silent?: boolean;
}

/** Everything a list page needs to render rows and drive its `DataTable`. */
export interface UseTableQueryResult<T> {
  /** The current page of rows returned by the fetcher. */
  rows: T[];
  /**
   * True while there are no rows to show for the current query — on mount and
   * after an offset/sort/filter change. Drives the table skeleton. A `reload`
   * leaves it false, so the table keeps rendering the rows it already has.
   */
  loading: boolean;
  /**
   * True while a fetch the user should see is in flight — the query load or a
   * plain {@link UseTableQueryResult.reload}, but never a silent one. Drives the
   * header's refresh spinner.
   */
  refreshing: boolean;
  /** Human-readable error message from the last failed fetch, or null. */
  error: string | null;
  /** Current pagination offset. */
  offset: number;
  /** Active single-column sort directive, or null for the server default order. */
  sort: SortSpec | null;
  /** Active filter directives. */
  filters: FilterSpec[];
  /** Update the pagination offset (accepts a value or updater function). */
  setOffset: Dispatch<SetStateAction<number>>;
  /** Set the sort directive; resets the offset to the first page. */
  setSort: (sort: SortSpec | null) => void;
  /** Set the filter directives; resets the offset to the first page. */
  setFilters: (filters: FilterSpec[]) => void;
  /**
   * Re-run the fetch with the current query (e.g. after a delete), keeping the
   * current rows visible until the new ones land.
   */
  reload: (options?: ReloadOptions) => Promise<void>;
}

/** Tuning knobs for {@link useTableQuery}. */
export interface UseTableQueryOptions {
  /** Page size passed to the fetcher. Defaults to 20. */
  limit?: number;
  /** Fallback error message when the thrown error is not an `Error`. */
  errorMessage?: string;
}

/**
 * Manage the pagination, sort, and filter state for an admin list page and run
 * the matching list fetch whenever any of them change.
 *
 * The `fetcher` is read through a ref, so callers may pass a fresh inline
 * function each render (e.g. `(q) => listUsers(q)`) without triggering refetch
 * loops. Changing `sort` or `filters` resets the offset to the first page so the
 * user is never stranded on an out-of-range page.
 *
 * Only a query change raises `loading`; a `reload` swaps the rows in place under
 * the `refreshing` flag. That keeps a refresh — and especially a poll loop —
 * from flashing the table back to its skeleton on every fetch.
 *
 * @param fetcher - Resolves a page of rows for the given {@link ListQuery}.
 * @param options - Optional page size and fallback error message.
 * @returns Reactive list state plus setters wired for a `DataTable`.
 */
export function useTableQuery<T>(
  fetcher: (query: ListQuery) => Promise<T[]>,
  { limit = 20, errorMessage = "Failed to load data" }: UseTableQueryOptions = {}
): UseTableQueryResult<T> {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [sort, setSortState] = useState<SortSpec | null>(null);
  const [filters, setFiltersState] = useState<FilterSpec[]>([]);

  // Keep the latest fetcher without making it a `load` dependency, so inline
  // fetchers do not retrigger the effect on every render.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(
    async ({ silent = false }: ReloadOptions = {}) => {
      if (!silent) setRefreshing(true);
      setError(null);
      try {
        setRows(await fetcherRef.current({ limit, offset, sort, filters }));
      } catch (e) {
        setError(e instanceof Error ? e.message : errorMessage);
      } finally {
        // The rows on screen now answer the current query, whichever way the
        // fetch went: on failure the error banner explains the stale ones.
        setLoading(false);
        if (!silent) setRefreshing(false);
      }
    },
    [limit, offset, sort, filters, errorMessage]
  );

  // `load` is recreated only when the query changes, so this effect fires on
  // mount and on every query change — exactly when the rows on screen no longer
  // answer the query and the skeleton is the honest thing to show.
  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const setSort = useCallback((next: SortSpec | null) => {
    setSortState(next);
    setOffset(0);
  }, []);

  const setFilters = useCallback((next: FilterSpec[]) => {
    setFiltersState(next);
    setOffset(0);
  }, []);

  return {
    rows,
    loading,
    refreshing,
    error,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload: load,
  };
}
