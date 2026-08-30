import { act, renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import type { ReactNode } from "react";
import { Provider } from "react-redux";
import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { store as appStore } from "@/store";
import { setUser } from "@/store/authSlice";
import { ADMIN, DEVELOPER, SUPER_ADMIN } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { makeStore } from "@/test/test-utils";
import { useTenantNames } from "./useTenantNames";

const TENANTS_URL = "http://localhost:8000/api/v1/tenants";

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

describe("useTenantNames", () => {
  it("resolves ids to display names for a super_admin", async () => {
    const queries: string[][] = [];
    server.use(
      http.get(TENANTS_URL, ({ request }) => {
        queries.push(new URL(request.url).searchParams.getAll("q"));
        return envelope([TENANT]);
      })
    );
    const { Wrapper } = wrapperFor(SUPER_ADMIN);

    const { result } = renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.get("tenant-1")).toBe("Acme Corp"));
    expect(queries).toEqual([["id:in:tenant-1"]]);
  });

  it.each([
    ["a developer", DEVELOPER],
    ["an admin", ADMIN],
  ])("issues no request and stays empty for %s", async (_who, state) => {
    let called = false;
    server.use(
      http.get(TENANTS_URL, () => {
        called = true;
        return envelope([]);
      })
    );
    const { Wrapper } = wrapperFor(state);

    const { result } = renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(called).toBe(false);
    expect(result.current.size).toBe(0);
  });

  it("does not raise an error toast for a non-super_admin", async () => {
    server.use(
      http.get(TENANTS_URL, () =>
        envelopeErr("FORBIDDEN", "Requires one of the roles: super_admin", 403)
      )
    );
    const toastsBefore = appStore.getState().toast.items.length;
    const { Wrapper } = wrapperFor(DEVELOPER);

    renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(appStore.getState().toast.items).toHaveLength(toastsBefore);
  });

  it("skips the request when no non-falsy ids remain, regardless of role", () => {
    let called = false;
    server.use(
      http.get(TENANTS_URL, () => {
        called = true;
        return envelope([]);
      })
    );
    const { Wrapper } = wrapperFor(SUPER_ADMIN);

    const { result } = renderHook(() => useTenantNames([null, undefined, ""]), {
      wrapper: Wrapper,
    });

    expect(called).toBe(false);
    expect(result.current.size).toBe(0);
  });

  it("resolves once the super_admin role arrives after mount", async () => {
    server.use(http.get(TENANTS_URL, () => envelope([TENANT])));
    const { store, Wrapper } = wrapperFor();

    const { result } = renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.size).toBe(0);

    act(() => {
      store.dispatch(setUser({ id: "u1", roles: ["super_admin"] } as User));
    });

    await waitFor(() => expect(result.current.get("tenant-1")).toBe("Acme Corp"));
  });

  it("keeps previously resolved names when a super_admin lookup fails", async () => {
    server.use(http.get(TENANTS_URL, () => envelopeErr("INTERNAL_ERROR", "boom", 500)));
    const { Wrapper } = wrapperFor(SUPER_ADMIN);

    const { result } = renderHook(() => useTenantNames(["tenant-1"]), { wrapper: Wrapper });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.size).toBe(0);
  });
});
