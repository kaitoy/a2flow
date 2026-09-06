/** @module useIsAllTenantsView.test — the hook gating the cross-tenant Tenant column. */
import { renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { Provider } from "react-redux";
import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { ALL_TENANTS_SENTINEL } from "@/store/authSlice";
import { makeStore } from "@/test/test-utils";
import { useIsAllTenantsView } from "./useIsAllTenantsView";

/** The real actor behind an active impersonation. */
const ACTOR = { id: "actor-1", roles: ["super_admin"] } as User;

/** Build a preloaded auth slice with the given tenant selection and impersonation actor. */
function authState(
  selectedTenantId: string | null,
  impersonatedBy: User | null = null
): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles: ["super_admin"] } as User,
      status: "authenticated",
      selectedTenantId,
      impersonatedUserId: impersonatedBy ? "target-1" : null,
      impersonatedBy,
    },
  };
}

/** Render `useIsAllTenantsView` against a fresh store seeded with `preloadedState`. */
function renderWith(preloadedState: Partial<RootState>) {
  const store = makeStore(preloadedState);
  const Wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children);
  return renderHook(() => useIsAllTenantsView(), { wrapper: Wrapper });
}

describe("useIsAllTenantsView", () => {
  it("is true when the All tenants sentinel is selected and no impersonation is active", () => {
    const { result } = renderWith(authState(ALL_TENANTS_SENTINEL));
    expect(result.current).toBe(true);
  });

  it("is false while impersonating, even with the All tenants sentinel still selected", () => {
    const { result } = renderWith(authState(ALL_TENANTS_SENTINEL, ACTOR));
    expect(result.current).toBe(false);
  });

  it("is false when a single tenant is selected", () => {
    const { result } = renderWith(authState("tenant-1"));
    expect(result.current).toBe(false);
  });

  it("is false when no tenant is selected", () => {
    const { result } = renderWith(authState(null));
    expect(result.current).toBe(false);
  });
});
