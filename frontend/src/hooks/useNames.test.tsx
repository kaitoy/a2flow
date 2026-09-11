import { act, renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { setUser } from "@/store/authSlice";
import { DEVELOPER, SUPER_ADMIN } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { makeStore } from "@/test/test-utils";
import { useGroupNames, useNames, useTenantNames, useUserNames } from "./useNames";

const API = "http://localhost:8000/api/v1";

/** The minimal user-group shape the resolver reads out of the list response. */
function group(id: string, name: string) {
  return {
    id,
    name,
    tenantId: "tenant-1",
    description: null,
    roles: [],
    memberIds: [],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

/** A full tenant row — every field the response schema validates against. */
const TENANT = {
  id: "tenant-1",
  displayName: "Acme Corp",
  name: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** A `<Provider>` wrapper over a fresh store seeded with `preloadedState`. */
function wrapperFor(preloadedState?: Partial<RootState>) {
  const store = makeStore(preloadedState);
  function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  }
  return { store, Wrapper };
}

describe("useNames", () => {
  it("resolves the deduplicated, sorted set of ids once and re-resolves when it changes", async () => {
    const resolve = vi.fn(
      async (ids: string[]) => new Map(ids.map((id) => [id, id.toUpperCase()]))
    );

    const { result, rerender } = renderHook(({ ids }) => useNames(ids, resolve), {
      initialProps: { ids: ["b", "a", "b", null, ""] as (string | null)[] },
    });
    await waitFor(() => expect(result.current.get("a")).toBe("A"));
    expect(resolve).toHaveBeenCalledWith(["a", "b"]);

    // A re-render with the same set in another order must not refetch.
    rerender({ ids: ["a", "b"] });
    expect(resolve).toHaveBeenCalledTimes(1);

    rerender({ ids: ["a", "b", "c"] });
    await waitFor(() => expect(result.current.get("c")).toBe("C"));
    expect(resolve).toHaveBeenCalledTimes(2);
  });

  it("skips the lookup when no ids remain or when disabled", () => {
    const resolve = vi.fn(async () => new Map<string, string>());

    renderHook(() => useNames([null, undefined, ""], resolve));
    renderHook(() => useNames(["a"], resolve, false));

    expect(resolve).not.toHaveBeenCalled();
  });

  it("keeps the previously resolved names when the lookup fails", async () => {
    const resolve = vi.fn(async () => {
      throw new Error("boom");
    });

    const { result } = renderHook(() => useNames(["a"], resolve));

    await new Promise((r) => setTimeout(r, 0));
    expect(result.current.size).toBe(0);
  });
});

describe("the per-record hooks", () => {
  it("useUserNames resolves through POST /users/resolve-names", async () => {
    server.use(
      http.post(`${API}/users/resolve-names`, async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        return envelope(ids.map((id) => ({ id, displayName: id.toUpperCase() })));
      })
    );

    const { result } = renderHook(() => useUserNames(["user-1", "user-2"]));

    await waitFor(() => expect(result.current.get("user-2")).toBe("USER-2"));
  });

  it("useGroupNames resolves through the list endpoint with an id:in: filter", async () => {
    const queries: (string | null)[] = [];
    server.use(
      http.get(`${API}/user-groups`, ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q"));
        return envelope([group("group-1", "Approvers"), group("group-2", "Reviewers")]);
      })
    );

    const { result } = renderHook(() => useGroupNames(["group-2", "group-1"]));

    await waitFor(() => expect(result.current.get("group-1")).toBe("Approvers"));
    expect(queries).toEqual(["id:in:group-1,group-2"]);
  });

  it("useTenantNames asks only as a super_admin, and once the role arrives", async () => {
    let called = 0;
    server.use(
      http.get(`${API}/tenants`, () => {
        called += 1;
        return envelope([TENANT]);
      })
    );
    const developer = wrapperFor(DEVELOPER);
    const { result: asDeveloper } = renderHook(() => useTenantNames(["tenant-1"]), {
      wrapper: developer.Wrapper,
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(called).toBe(0);
    expect(asDeveloper.current.size).toBe(0);

    const { store, Wrapper } = wrapperFor();
    const { result } = renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });
    act(() => {
      store.dispatch(setUser({ id: "u1", roles: ["super_admin"] } as User));
    });
    await waitFor(() => expect(result.current.get("tenant-1")).toBe("Acme Corp"));

    const admin = wrapperFor(SUPER_ADMIN);
    const { result: asAdmin } = renderHook(() => useTenantNames(["tenant-1"]), {
      wrapper: admin.Wrapper,
    });
    await waitFor(() => expect(asAdmin.current.get("tenant-1")).toBe("Acme Corp"));
  });
});
