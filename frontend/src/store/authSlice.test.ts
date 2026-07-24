import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";

const STORAGE_KEY = "a2flow.selectedTenantId";
const IMPERSONATED_STORAGE_KEY = "a2flow.impersonatedUserId";

const TARGET = { id: "target-1", username: "target" } as User;
const ACTOR = { id: "actor-1", username: "actor" } as User;

describe("authSlice", () => {
  beforeEach(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(IMPERSONATED_STORAGE_KEY);
    vi.resetModules();
  });

  afterEach(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(IMPERSONATED_STORAGE_KEY);
  });

  it("defaults selectedTenantId to null when nothing is persisted", async () => {
    const { default: authReducer } = await import("./authSlice");
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state.selectedTenantId).toBeNull();
  });

  it("seeds selectedTenantId from localStorage on load", async () => {
    window.localStorage.setItem(STORAGE_KEY, "tenant-1");
    const { default: authReducer } = await import("./authSlice");
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state.selectedTenantId).toBe("tenant-1");
  });

  it("setSelectedTenantId updates the selection", async () => {
    const { default: authReducer, setSelectedTenantId } = await import("./authSlice");
    const state = authReducer(undefined, setSelectedTenantId("tenant-2"));
    expect(state.selectedTenantId).toBe("tenant-2");
  });

  it("clearUser resets the selection to null", async () => {
    const { default: authReducer, clearUser, setSelectedTenantId } = await import("./authSlice");
    const withSelection = authReducer(undefined, setSelectedTenantId("tenant-2"));
    const cleared = authReducer(withSelection, clearUser());
    expect(cleared.selectedTenantId).toBeNull();
  });

  it("defaults impersonatedUserId to null when nothing is persisted", async () => {
    const { default: authReducer } = await import("./authSlice");
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state.impersonatedUserId).toBeNull();
  });

  it("seeds impersonatedUserId from localStorage on load", async () => {
    window.localStorage.setItem(IMPERSONATED_STORAGE_KEY, "target-1");
    const { default: authReducer } = await import("./authSlice");
    const state = authReducer(undefined, { type: "@@INIT" });
    expect(state.impersonatedUserId).toBe("target-1");
  });

  it("setMe sets the effective user and the real actor", async () => {
    const { default: authReducer, setMe } = await import("./authSlice");
    const state = authReducer(undefined, setMe({ user: TARGET, impersonatedBy: ACTOR }));
    expect(state.user).toEqual(TARGET);
    expect(state.status).toBe("authenticated");
    expect(state.impersonatedBy).toEqual(ACTOR);
  });

  it("setMe with a null impersonatedBy self-heals a stale impersonatedUserId", async () => {
    window.localStorage.setItem(IMPERSONATED_STORAGE_KEY, "target-1");
    const { default: authReducer, setMe } = await import("./authSlice");
    const initial = authReducer(undefined, { type: "@@INIT" });
    expect(initial.impersonatedUserId).toBe("target-1");

    const state = authReducer(initial, setMe({ user: ACTOR, impersonatedBy: null }));
    expect(state.impersonatedUserId).toBeNull();
    expect(state.impersonatedBy).toBeNull();
  });

  it("clearImpersonation clears impersonation state without touching the session", async () => {
    const { default: authReducer, setMe, clearImpersonation } = await import("./authSlice");
    const impersonating = authReducer(undefined, setMe({ user: TARGET, impersonatedBy: ACTOR }));
    const cleared = authReducer(impersonating, clearImpersonation());
    expect(cleared.impersonatedUserId).toBeNull();
    expect(cleared.impersonatedBy).toBeNull();
    expect(cleared.user).toEqual(TARGET);
    expect(cleared.status).toBe("authenticated");
  });

  it("clearUser also resets impersonation state", async () => {
    const { default: authReducer, setMe, clearUser } = await import("./authSlice");
    const impersonating = authReducer(undefined, setMe({ user: TARGET, impersonatedBy: ACTOR }));
    const cleared = authReducer(impersonating, clearUser());
    expect(cleared.impersonatedUserId).toBeNull();
    expect(cleared.impersonatedBy).toBeNull();
  });
});
