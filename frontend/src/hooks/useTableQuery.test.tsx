import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ListQuery } from "@/lib/api";
import { useTableQuery } from "./useTableQuery";

describe("useTableQuery", () => {
  it("loads rows on mount with the configured limit", async () => {
    const fetcher = vi.fn(async (_q: ListQuery) => [{ id: "1" }]);
    const { result } = renderHook(() => useTableQuery(fetcher, { limit: 10 }));
    await waitFor(() => expect(result.current.rows).toEqual([{ id: "1" }]));
    expect(fetcher).toHaveBeenCalledWith({ limit: 10, offset: 0, sort: null, filters: [] });
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
