import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ListQuery } from "@/lib/api";
import { useTableQuery } from "./useTableQuery";

interface Row {
  id: string;
}

/** A promise plus the handle to settle it, for holding a fetch open mid-test. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/**
 * A fetcher that resolves the first call with `first` and holds every later call
 * open until the returned `resolve` is called with the rows to swap in.
 */
function fetcherHoldingTheReload(first: Row[]) {
  const held = deferred<Row[]>();
  let calls = 0;
  const fetcher = vi.fn((_q: ListQuery): Promise<Row[]> => {
    calls += 1;
    return calls === 1 ? Promise.resolve(first) : held.promise;
  });
  return { fetcher, resolve: held.resolve };
}

describe("useTableQuery", () => {
  it("loads rows on mount with the configured limit", async () => {
    const fetcher = vi.fn(async (_q: ListQuery) => [{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(result.current.rows).toEqual([{ id: "1" }]));
    expect(fetcher).toHaveBeenCalledWith({ limit: 10, offset: 0, sort: null, filters: [] });
  });

  it("is loading until the first page lands", async () => {
    const fetcher = vi.fn(async (_q: ListQuery) => [{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it("keeps the rows and skips the skeleton while a reload is in flight", async () => {
    const { fetcher, resolve } = fetcherHoldingTheReload([{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      void result.current.reload();
    });
    await waitFor(() => expect(result.current.refreshing).toBe(true));
    expect(result.current.loading).toBe(false);
    expect(result.current.rows).toEqual([{ id: "1" }]);

    await act(async () => {
      resolve([{ id: "2" }]);
    });
    await waitFor(() => expect(result.current.rows).toEqual([{ id: "2" }]));
    expect(result.current.refreshing).toBe(false);
  });

  it("raises no indicator at all during a silent reload", async () => {
    const { fetcher, resolve } = fetcherHoldingTheReload([{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      void result.current.reload({ silent: true });
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(false);
    expect(result.current.rows).toEqual([{ id: "1" }]);

    await act(async () => {
      resolve([{ id: "2" }]);
    });
    await waitFor(() => expect(result.current.rows).toEqual([{ id: "2" }]));
    expect(result.current.refreshing).toBe(false);
  });

  it("shows the skeleton again when the query changes", async () => {
    const fetcher = vi.fn(async (_q: ListQuery) => [{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setSort({ field: "name", descending: false }));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it("resets the offset to the first page when sort changes", async () => {
    const fetcher = vi.fn(async (_q: ListQuery) => [] as { id: string }[]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(fetcher).toHaveBeenCalled());

    act(() => result.current.setOffset(20));
    await waitFor(() => expect(result.current.offset).toBe(20));

    act(() => result.current.setSort({ field: "name", descending: false }));
    await waitFor(() => expect(result.current.offset).toBe(0));
    expect(result.current.sort).toEqual({ field: "name", descending: false });
  });

  it("captures an error message when the fetch fails", async () => {
    const fetcher = vi.fn(async (_q: ListQuery): Promise<{ id: string }[]> => {
      throw new Error("boom");
    });
    const { result } = renderHook(() => useTableQuery(fetcher, { errorMessage: "fallback" }));
    await waitFor(() => expect(result.current.error).toBe("boom"));
  });
});
