import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { useUserNames } from "./useUserNames";

describe("useUserNames", () => {
  it("resolves the given ids to display names", async () => {
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        return envelope(ids.map((id) => ({ id, displayName: id.toUpperCase() })));
      })
    );

    const { result } = renderHook(() => useUserNames(["user-1", "user-2"]));

    await waitFor(() => expect(result.current.get("user-1")).toBe("USER-1"));
    expect(result.current.get("user-2")).toBe("USER-2");
  });

  it("filters out falsy ids and skips the request when none remain", () => {
    let called = false;
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", () => {
        called = true;
        return envelope([]);
      })
    );

    const { result } = renderHook(() => useUserNames([null, undefined, ""]));

    expect(result.current.size).toBe(0);
    expect(called).toBe(false);
  });

  it("re-resolves when the set of ids changes", async () => {
    const requests: string[][] = [];
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        requests.push(ids);
        return envelope(ids.map((id) => ({ id, displayName: id.toUpperCase() })));
      })
    );

    const { result, rerender } = renderHook(({ ids }) => useUserNames(ids), {
      initialProps: { ids: ["user-1"] },
    });
    await waitFor(() => expect(result.current.get("user-1")).toBe("USER-1"));

    rerender({ ids: ["user-1", "user-2"] });
    await waitFor(() => expect(result.current.get("user-2")).toBe("USER-2"));

    expect(requests).toEqual([["user-1"], ["user-1", "user-2"]]);
  });

  it("keeps the previously resolved names when the lookup fails", async () => {
    server.use(
      http.post("http://localhost:8000/api/v1/users/resolve-names", () =>
        envelopeErr("internal_error", "boom", 500)
      )
    );

    const { result } = renderHook(() => useUserNames(["user-1"]));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.size).toBe(0);
  });
});
