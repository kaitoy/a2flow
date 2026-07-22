import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const STORAGE_KEY = "a2flow.selectedTenantId";

describe("authSlice", () => {
  beforeEach(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    vi.resetModules();
  });

  afterEach(() => {
    window.localStorage.removeItem(STORAGE_KEY);
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
});
