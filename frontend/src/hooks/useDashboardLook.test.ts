import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DASHBOARD_LOOK_STORAGE_KEY, useDashboardLook } from "./useDashboardLook";

beforeEach(() => {
  window.localStorage.removeItem(DASHBOARD_LOOK_STORAGE_KEY);
});

describe("useDashboardLook", () => {
  it("is the standard look until the viewer chooses otherwise", () => {
    const { result } = renderHook(() => useDashboardLook());
    expect(result.current[0]).toBe("standard");
  });

  it("opens in the look stored by an earlier visit", () => {
    window.localStorage.setItem(DASHBOARD_LOOK_STORAGE_KEY, "console");
    const { result } = renderHook(() => useDashboardLook());
    expect(result.current[0]).toBe("console");
  });

  it("changes the look and remembers it", () => {
    const { result } = renderHook(() => useDashboardLook());
    act(() => result.current[1]("console"));
    expect(result.current[0]).toBe("console");
    expect(window.localStorage.getItem(DASHBOARD_LOOK_STORAGE_KEY)).toBe("console");
  });
});
