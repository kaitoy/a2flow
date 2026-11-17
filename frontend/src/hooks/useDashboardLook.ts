/** @module useDashboardLook — which of the dashboard's two looks the viewer chose, persisted to localStorage. */
"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * How `/dashboard` is drawn: `"standard"` follows the app's design system and
 * theme like every other screen, `"console"` is Mission Control — always
 * dark, glowing, and moving at rest.
 */
export type DashboardLook = "standard" | "console";

/** localStorage key holding the viewer's choice of look. */
export const DASHBOARD_LOOK_STORAGE_KEY = "a2flow.dashboard.look";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function readLook(): DashboardLook {
  try {
    return window.localStorage.getItem(DASHBOARD_LOOK_STORAGE_KEY) === "console"
      ? "console"
      : "standard";
  } catch {
    return "standard";
  }
}

const serverLook = (): DashboardLook => "standard";

/**
 * The viewer's dashboard look and a setter for it. The choice lives in
 * localStorage under {@link DASHBOARD_LOOK_STORAGE_KEY}, so it is per browser
 * and shared by every tab; `"standard"` until one is made.
 *
 * It is read through `useSyncExternalStore` rather than an effect, so a
 * client-side navigation to the dashboard paints the chosen look on the first
 * frame instead of flashing the default. Only a hard reload hydrates as
 * `"standard"` first.
 *
 * ponytail: localStorage is the only store, so where it refuses writes
 * (some privacy modes) the look cannot be changed. Add an in-memory fallback
 * if that ever matters.
 *
 * @returns The current look and a function that changes and persists it.
 */
export function useDashboardLook(): [DashboardLook, (look: DashboardLook) => void] {
  const look = useSyncExternalStore(subscribe, readLook, serverLook);
  const setLook = useCallback((next: DashboardLook) => {
    try {
      window.localStorage.setItem(DASHBOARD_LOOK_STORAGE_KEY, next);
    } catch {
      // Ignore -- privacy-mode browsers may throw on localStorage writes.
    }
    // The browser only tells *other* tabs about a write; tell this one too.
    window.dispatchEvent(new StorageEvent("storage", { key: DASHBOARD_LOOK_STORAGE_KEY }));
  }, []);
  return [look, setLook];
}
